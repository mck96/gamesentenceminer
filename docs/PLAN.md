# Oyun Ekranı OCR + Çeviri Aracı: Plan (Taslak v0.3)

## 0. Alınan kararlar

| Konu | Karar |
|---|---|
| Arayüz | **OBS Studio tarzı.** Kaynak seçilir, oyun görüntüsü önizlemede görünür, metin alanları önizleme üstüne dikdörtgen olarak çizilir. Birden fazla bölge desteklenir |
| Oyun dilleri | Ağırlıklı İngilizce, Japonca, Çince |
| Çeviri hedefi | Türkçe ve İngilizce (profil başına seçilir, ikisi birden de gösterilebilir) |
| Oyun tarzı | Her tür oyun, genelde **tam ekran** |
| Donanım | **Tek monitör**, RTX 4070 |
| Platform | **Wayland öncelikli.** Hedef Ubuntu 26.04 (GNOME 50, sadece Wayland). Geçişe kadar 24.04 Wayland'da da çalışır. Xorg'a geçmeye gerek yok |
| Çeviri servisi | MVP anahtarsız Google ile başlar, DeepL anahtarı gelince varsayılan olur |
| Dil öğrenme | Sonraki aşama. Anki ilk aşamada yok, veri modeli şimdiden buna uygun tutulur (bkz. §9) |

## 1. Hedef

Oyun oynarken ekrandaki metin alanlarını (diyalog kutusu, konuşan kişinin adı,
altyazı, menü) yakalayan, OCR ile okuyan ve anında çeviren bir masaüstü aracı.
En önemli kısıt: **hafif olmalı**, oyun oynarken bilgisayarı zorlamamalı.

## 2. Hafiflik ilkeleri

Programın neredeyse tüm maliyeti OCR'dan gelir. Bu yüzden asıl iş OCR'ı mümkün
olduğunca az çalıştırmak:

1. **Ekran akışı düşük FPS'te istenir** (ör. en fazla 5 FPS). Her karede sadece
   çizilen bölgeler kırpılır (numpy dilimleme, kopyasız).
2. **OCR sadece metin değişip sabitlendiğinde çalışır.** Değişim algılama çok
   ucuz (küçültülmüş gri görüntüde kare farkı, < 1 ms).
3. **Daktilo efekti bitene kadar bekle.** Bölge K kare sabit kalınca tek bir OCR
   yapılır.
4. **OCR varsayılan olarak CPU'da çalışır**, 1-2 thread ile ve düşük öncelikte
   (`nice`). RTX 4070 için GPU seçeneği de olacak (bkz. §7).
5. **Önizleme ve akış bedava değildir.** Canlı önizleme sadece düzenleyici
   görünürken çalışır. Oyun modu kapalıyken ekran akışı tamamen durur.
6. **Tekrar yok.** Benzer metin tekrar OCR'lanmaz veya çevrilmez, çeviriler
   SQLite'ta önbelleğe alınır.
7. **Birikme yok.** Kuyruklar tek elemanlı: OCR yetişemezse eski kare atılır.
8. **Tembel yükleme.** Modeller ilk ihtiyaçta yüklenir.

**Hedef bütçe** (Faz 0'da ölçülecek):

| Ölçüt | Hedef |
|---|---|
| Oyun sırasında, metin değişmiyorken CPU | tek çekirdeğin %1-2'si altı |
| Oyunun FPS'ine etkisi (ekran akışı açıkken) | fark edilmeyecek kadar az |
| RAM | ~300-400 MB altı |
| Metin değişiminden çevirinin görünmesine | ~1 sn altı |

## 3. Arayüz: OBS tarzı düzenleyici

OBS'un kendisini kullanmıyoruz, çünkü bu iş için gereksiz ağır. Sadece arayüz
mantığını alıyoruz: **kaynak → önizleme → bölgeler**.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Profil: [Örnek Oyun v]   Kaynak: [Ekran 1 v]   [Canlı|Dondur]  [Başlat]  │
├──────────────┬────────────────────────────────────────┬──────────────────┤
│ Kaynaklar    │                                        │ Bölgeler         │
│ (o) Ekran 1  │      ÖNİZLEME (oyunun görüntüsü)       │ ■ diyalog  oto   │
│ ( ) Pencere  │                                        │ ■ isim   bağlı   │
│              │  ┌─ isim ──────┐                       │ ■ menü  kısayol  │
│              │  └─────────────┘                       │ [+ Yeni] [Öner]  │
│              │  ┌─ diyalog ─────────────────────────┐ │                  │
│              │  │                                   │ │ Seçili bölge:    │
│              │  └───────────────────────────────────┘ │  dil, mod, FPS   │
│              │                       ┌─ menü ───┐     │  ön işleme       │
│              │                       └──────────┘     │ [Test OCR]       │
├──────────────┴────────────────────────────────────────┴──────────────────┤
│ Son satırlar:                                                            │
│  [isim] Where are you going?  ->  Nereye gidiyorsun?                     │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Kaynaklar
- **Ekran (monitör):** Varsayılan kaynak. Tam ekran oyunda monitör görüntüsü
  zaten oyunun kendisidir.
- **Pencere:** Pencereli oyunlar için. Wayland'da portal pencere paylaşımına izin
  veriyor (OBS'taki gibi), Faz 3'te eklenir.

### 3.2 Bölgeler (birden fazla)
- Önizleme üstünde fareyle çizilir. Taşınabilir, köşelerinden boyutlandırılır,
  her biri adlandırılır ve renklendirilir.
- Koordinatlar kaynağa göre oransal (0-1) saklanır.
- Her bölgenin bir **modu** vardır:

| Mod | Ne zaman | Örnek |
|---|---|---|
| `oto` | Bölge izlenir, metin değişip sabitlenince okunur | Diyalog kutusu, altyazı |
| `bağlı` | Kendisi izlenmez. Bağlı olduğu bölge tetiklenince onunla birlikte okunur | Konuşan kişinin adı |
| `kısayol` | Sadece kısayola basınca okunur | Menü, eşya açıklaması |

- **[Test OCR]:** Seçili bölgeyi o anki karede hemen okur ve çevirir.
- **[Öner]** (sonraki faz): O karede bir kez metin tespiti çalıştırıp aday
  kutular önerir.

### 3.3 Tek monitör: "dondur" akışı (birincil)

Tek monitörde tam ekran oyun oynarken önizlemeyi aynı anda göremezsin. Bu yüzden
bölge çizme akışı dondurulmuş kare üzerinden yürür:

1. Oyun açıkken kısayola basılır (ör. `Ctrl+Alt+E`) ve o anki kare dondurulur.
2. Alt+Tab ile düzenleyiciye geçilir. GNOME, arka plandaki uygulamaların kendi
   penceresini öne getirmesini kısıtlayabildiği için geçiş elle yapılır.
3. Dikdörtgenler dondurulmuş kare üzerinde 1:1 netlikte çizilir, [Test OCR] ile
   denenir ve kaydedilir.
4. Alt+Tab ile oyuna dönülür. Bölgeler artık arka planda izleniyor.

Profil oyun başına bir kez hazırlanır, sonra sadece [Başlat] denir. "Canlı"
önizleme pencereli oyunlarda ve ayar yaparken işe yarar.

## 4. Çeviriyi gösterme: tam ekran oyunun üstünde overlay

Tek monitör olduğu için **ana gösterim overlay'dir**:

- **Banner:** ekranın altında altyazı şeridi
- **Yerinde:** ilgili bölgenin hemen altında veya üstünde

Overlay yarı saydamdır ve tıklamaları oyuna geçirir. Wayland'da en zor kısım bu
(bkz. §6.3). Yöntem Faz 0'da test edilip seçilecek.

Ek gösterimler:
- Düzenleyicinin "son satırlar" paneli
- Pano (isteğe bağlı)
- İleride telefondan açılabilen yerel web sayfası (§9). Tek monitör için iyi bir
  "ikinci ekran" olur.

## 5. Mimari

**Teknoloji:**
- Python + PySide6 (Qt).
- Python, **uv ile proje-özel bir sürüm (3.12)** olarak kullanılır. Böylece sistem
  Python'una bağlı kalınmaz, 24.04 → 26.04 geçişinde ortam bozulmaz.
- Wayland ekran yakalama için PyGObject (Gio D-Bus + GStreamer) ve
  `gstreamer1.0-pipewire` kullanılır.

```
 Düzenleyici (OBS tarzı) ──► Profil: kaynak + bölgeler + ayarlar
                                   │
                                   ▼
 Portal + PipeWire akışı (≤5 FPS) ─► Bölge kırpma ─► Değişim algılama ─► Stabilite ─► OCR
                                                                                     │
 Overlay / panel / pano ◄── Çevirmen (+önbellek) ◄── Tekrar filtresi ◄───────────────┤
                                                                                     ▼
                                                                Satır geçmişi (SQLite + kırpıntı)

 Tetikleyiciler: Tray · GNOME özel kısayolu → `gsm` CLI → IPC · (26.04) GlobalShortcuts portalı
```

**Modül yapısı** (paket adı geçici):

```
src/gamesentenceminer/
  app.py                # giriş noktası, tray, ana döngü
  config.py             # ayarlar + oyun profilleri (TOML)
  capture/
    base.py             # CaptureBackend: start(), latest_frame(), stop()
    portal.py           # xdg-desktop-portal ScreenCast oturumu + restore token
    pipewire_stream.py  # GStreamer pipewiresrc → appsink (numpy kare)
    x11.py              # isteğe bağlı: mss (24.04 Xorg kullanıcıları için)
  editor/
    window.py           # OBS tarzı ana pencere
    canvas.py           # önizleme + dikdörtgen çizme/taşıma/boyutlandırma
    suggest.py          # [Öner]: tek seferlik metin tespiti (Faz 4)
  pipeline/
    watcher.py          # değişim algılama + stabilite kapısı
    dedup.py            # benzer metin filtresi
    langdetect.py       # yazı sistemi tespiti: kana → ja, sadece Han → zh, Latin → en
  ocr/
    base.py  rapid.py  meiki.py  tesseract.py
  translate/
    base.py  google.py  deepl.py  llm.py  offline.py  cache.py
  overlay/
    banner.py  inplace.py
  hotkeys/
    ipc.py              # Unix socket sunucusu
    cli.py              # `gsm freeze`, `gsm trigger`, `gsm pause`
    gnome_setup.py      # GNOME özel kısayollarını gsettings ile kurar
    portal_shortcuts.py # GNOME 48+ GlobalShortcuts portalı (26.04)
  store/
    history.py          # satır geçmişi (dil öğrenme için temel)
tests/
tools/
  bench.py              # OCR hız/doğruluk karşılaştırması
  spikes/               # Faz 0 deneme betikleri
  dev/                  # geliştirme araçları (ör. sahte ScreenCast portalı)
```

**Profil örneği** (`~/.config/gamesentenceminer/profiles/ornek-oyun.toml`):

```toml
[game]
name = "Örnek Oyun"
source = "monitor"              # monitor | window

[ocr]
engine = "rapid"                # rapid | meiki | tesseract
device = "cpu"                  # cpu | cuda
source_lang = "auto"            # auto | en | ja | zh

[translate]
engine = "google"               # google | deepl | llm | offline
target_langs = ["tr"]           # ["tr"], ["en"] veya ["tr", "en"]

[overlay]
style = "banner"                # banner | inplace | off

[[regions]]
name = "diyalog"
rect = [0.12, 0.72, 0.76, 0.20] # kaynağa göre oransal: x, y, genişlik, yükseklik
mode = "auto"                   # auto | linked | hotkey
stable_frames = 2
preprocess = ["scale2x", "grayscale"]

[[regions]]
name = "isim"
rect = [0.12, 0.66, 0.20, 0.05]
mode = "linked"
linked_to = "diyalog"
```

## 6. Wayland: OBS nasıl yapıyor, biz nasıl yapacağız

Wayland ekran yakalamayı yasaklamaz, **izne bağlar**. OBS de, biz de aynı resmi
yolu kullanıyoruz. Asıl fark, bizim aracın OBS'un yapmadığı iki şeye daha ihtiyaç
duyması:

| İş | OBS | Biz |
|---|---|---|
| Ekran yakalama | xdg-desktop-portal ScreenCast + PipeWire | **Aynısı** |
| Global kısayol | Yerleşik destek yok. Kısayollar sadece OBS odaktayken çalışıyor (eklentiyle portal kullanılabiliyor) | GNOME özel kısayolu → CLI. 26.04'te GlobalShortcuts portalı |
| Oyunun üstüne yazı çizmek | **Hiç yapmıyor**, gerekmiyor | Gerekli. Asıl zor kısım bu |

### 6.1 Ekran yakalama (OBS ile aynı yol)

1. Uygulama, D-Bus üzerinden `org.freedesktop.portal.ScreenCast` portalına
   bağlanır: `CreateSession` → `SelectSources(monitor, persist_mode=2,
   restore_token)` → `Start` → `OpenPipeWireRemote`.
2. **İlk seferde** GNOME'un "Ekran paylaşımı" penceresi açılır ve monitörü
   seçersin. Portalın döndürdüğü *restore token* kaydedilir, sonraki açılışlarda
   tekrar sorulmaz. OBS de böyle çalışıyor.
3. Portal bir PipeWire video akışı verir. GStreamer ile okunur:
   `pipewiresrc fd=… path=… ! videoconvert ! video/x-raw,format=BGRx ! appsink drop=true max-buffers=1`.
   Akış düşük FPS'te (ör. 5) istenir.
4. Her karede sadece bölgeler kırpılır.
5. Akış açıkken GNOME üst çubukta ekran paylaşımı simgesini gösterir. Bu normaldir.
   Oyun modu kapanınca akış durur ve simge kaybolur.

X11'den farkı: X11'de istenen dikdörtgen istendiği anda doğrudan okunur. Wayland'da
compositor bize sürekli bir akış gönderir, biz de onu kırparız. Compositor'ın bu
akışı üretmesinin küçük bir GPU maliyeti var. Düşük FPS'te önemsiz olması bekleniyor,
**Faz 0'da oyun FPS'i ile ölçülecek.**

### 6.2 Global kısayollar

Wayland'da uygulamalar, odakta değilken klavyeyi dinleyemez. Bu güvenlik
özelliğidir: bir oyun ya da tarayıcı arka planda tuşlarını okuyamaz.

- **Her iki sürümde çalışan yol (24.04 ve 26.04):** GNOME Ayarlar → Klavye → Özel
  Kısayollar. Kısayol `gsm freeze` / `gsm trigger` / `gsm pause` komutunu çalıştırır,
  komut da Unix socket ile çalışan uygulamaya iletir. Kurulum sihirbazı bu
  kısayolları `gsettings` ile otomatik ekler.
- **26.04 (GNOME 50):** GlobalShortcuts portalı. Uygulama kısayollarını kaydeder,
  GNOME bir kez onay ister ve tuşlar Ayarlar'dan değiştirilebilir.

### 6.3 Tam ekran oyunun üstünde overlay (asıl zorluk)

Wayland'da sıradan bir uygulama penceresinin konumunu seçemez ve "her zaman üstte"
duramaz. GNOME, diğer masaüstlerindeki overlay protokolünü (layer-shell)
desteklemiyor. Seçenekler, deneme sırasıyla:

| Yöntem | Nasıl | Artı | Eksi |
|---|---|---|---|
| **A: XWayland overlay** | Uygulama X11 uyumluluk katmanı üstünden çalışır (`QT_QPA_PLATFORM=xcb`). Overlay, pencere yöneticisini atlayan (override-redirect) ve tıklama geçiren bir penceredir | Kolay, ek bileşen yok. XWayland 26.04'te de var | GNOME'un bunu tam ekran oyunun üstünde gösterdiği doğrulanmalı |
| **B: GNOME Shell eklentisi** | Küçük bir eklenti overlay'i compositor'ın içinde çizer, uygulama ona D-Bus ile metin yollar | Her şeyin üstünde garanti. Kısayolları da üstlenebilir | GNOME sürümleri arasında bakım ister |
| **C: Yedekler** | Kenarlıksız pencere modu, telefonda web sayfası (§9) | Her durumda çalışır | Daha az konforlu |

Faz 0'da A senin makinende 2-3 oyunla test edilir. Çalışmazsa B'ye geçilir.

## 7. OCR motoru (EN / JA / ZH)

Motorlar takılıp çıkarılabilir (`OcrEngine` arayüzü), profil veya bölge başına
seçilir.

| Motor | Rolü | Neden |
|---|---|---|
| **RapidOCR (PP-OCRv5, ONNX)** | **Varsayılan, üç dil için** | Tek model Çince (basit + geleneksel), Japonca ve İngilizce okur. Çince'de alanının en iyilerinden. PyTorch gerekmez. İngilizce için ayrı bir PP-OCRv5 modeli de var |
| **meikiocr** | Japonca alternatif | Japon oyun metni ve piksel fontlar için eğitilmiş, küçük modeller |
| **Tesseract** | İngilizce, yedek | Çok hafif. Temiz fontlarda iyi, ön işleme ister |
| manga-ocr | İsteğe bağlı, ileride | Japoncada çok isabetli ama PyTorch ve ~1 GB+ RAM gerektirir |

- **CPU mu GPU mu (RTX 4070):**
  - ONNX Runtime'ın CUDA desteğiyle OCR GPU'da birkaç milisaniyeye iner ve birkaç
    yüz MB VRAM kullanır, 12 GB içinde önemsiz.
  - Varsayılan yine de CPU, çünkü CUDA kütüphaneleri kurulumu büyütüyor ve küçük
    kırpıntılarda CPU zaten yeterli.
  - `device = "cuda"` seçeneği olacak. Faz 0'da ikisi de ölçülecek.
- **Dil tespiti (`source_lang = "auto"`):** Metin kana içeriyorsa Japonca, sadece
  Han karakterleri varsa Çince, Latin harfleriyse İngilizce kabul edilir.
- **Ön işleme** (bölge başına): 2x büyütme, gri ton, eşikleme veya ters çevirme,
  metin rengine göre renk filtresi.

## 8. Çeviri (hedef: TR ve EN)

`Translator` arayüzü ile takılabilir:

- **Google (MVP, anahtarsız):** Resmi olmayan ücretsiz uç nokta. Başlangıç için
  yeterli ama bir gün bozulabilir.
- **DeepL API Free (anahtar gelince varsayılan):** Aylık 500k karakter, EN/JA/ZH
  → TR/EN destekli.
- **LLM API (Faz 4):** Bağlama duyarlı, oyunun tonunu koruyan çeviri. Önceki
  satırlar ve konuşan kişinin adı bağlam olarak gönderilir.
- **Çevrimdışı (Faz 4):**
  - Opus-MT / NLLB-200 (CTranslate2, int8).
  - RTX 4070 küçük bir yerel LLM'i de çalıştırabilir, ama oyunla GPU için
    yarışacağı için isteğe bağlı kalır.
- `target_langs = ["tr", "en"]` ile iki dil birden gösterilebilir.
- Her çeviri SQLite'ta önbelleğe alınır.

## 9. Dil öğrenmeye hazırlık (Anki'siz)

İlk aşamada Anki yok. Ama her okunan satır şimdiden şu bilgilerle kaydedilir:

| Alan | Örnek |
|---|---|
| Oyun / profil | Örnek Oyun |
| Zaman | 2026-10-08 21:14:03 |
| Konuşan | (`bağlı` isim bölgesinden) |
| Orijinal metin + dil | `どこへ行くの？` / ja |
| Çeviri(ler) | TR, EN |
| Bölge kırpıntısı | küçük WebP dosyası |

Sonraki aşamada bunun üstüne iki şey eklenir:

- **Yerel web sayfası:** Satırlar tarayıcıda akar ve Yomitan ile kelimelerin üstüne
  gelince sözlük açılır. Telefondan da açılabilir.
- **Anki:** Tek tuşla cümle + ekran görüntüsü + çeviriden kart oluşturulur.

## 10. Değişim algılama (hafifliğin kalbi)

Her `oto` bölge için, gelen her karede (≤5 FPS):

1. Bölge kırpılır, 1/4 ölçeğe küçültülüp griye çevrilir.
2. Önceki kareyle ortalama mutlak fark hesaplanır.
3. Fark eşiğin üstündeyse bölge "değişiyor" sayılır. Fark eşiğin altına inip
   `stable_frames` boyunca öyle kalırsa OCR tetiklenir. Bu bölgeye `bağlı`
   bölgeler de aynı karede okunur.
4. Bölgede neredeyse hiç kenar yoksa (diyalog kutusu kapalı) OCR yapılmaz.
5. OCR sonucu öncekine çok benziyorsa (normalize Levenshtein > 0.9) çeviri
   atlanır.

## 11. Fazlar

**Şu anki durum: Faz 0 kısmen tamam, Faz 1 MVP'nin ilk sürümü çalışıyor.**

Faz 0, senin makinende:
- Portal ile yakalama çalışıyor.
- GNOME düşük FPS isteğini kabul ediyor (en fazla 5 kare/sn).
- Bizim işlemci kullanımımız %0,7.
- İzin, paylaşım penceresinde "Bu seçimi anımsa" işaretliyse hatırlanıyor.
- Ayrıntılar [FAZ0.md](FAZ0.md)'de.

Faz 1 ilk sürümü (`uv run gsm`):
- OBS tarzı pencere, canlı/dondurulmuş önizleme, "dönünce dondur".
- Önizlemede çoklu bölge çizme, taşıma, boyutlandırma, silme.
- Değişim algılamalı otomatik okuma, RapidOCR (PP-OCRv6).
- Anahtarsız Google çevirisi, metin çıktısı paneli.
- Overlay şeridi, kendi metnini okumasın diye OCR'dan maskelenir.

Ölçümler (bulutta, oyun görüntüsü yerine görsel kullanılarak):
- 2560x1440 karede diyalog OCR'ı ~200 ms (2 iş parçacığı).
- Metin değişmezken işlemci kullanımı %1-2, RAM ~310 MB.

Kalanlar:
- Oyunla FPS ölçümü ve overlay testi (senin makinende).
- Kısayol → CLI → IPC.
- Gerçek ekran görüntüleriyle OCR karşılaştırması.

Not: Ekran yakalama, overlay ve GPU testleri senin masaüstünde çalışmalı. Bulut
geliştirme ortamı ekranına erişemez. Bu yüzden Faz 0 betiklerini ben yazarım, sen
çalıştırıp çıktıyı paylaşırsın.

| Faz | İçerik | Bitti sayılması için |
|---|---|---|
| **0: Teknik denemeler** | `tools/spikes/` altında: (1) portal + PipeWire ile 5 FPS yakalama: izin penceresi, restore token, CPU kullanımı, oyun FPS'ine etkisi. (2) Tam ekran oyun üstünde XWayland overlay ve tıklama geçirgenliği (Proton, yerel ve varsa emülatör oyunu). (3) GNOME özel kısayolu → CLI → IPC gecikmesi. (4) `tools/bench.py`: EN/JA/ZH ekran görüntüleriyle motor karşılaştırması, CPU ve CUDA | Overlay yöntemi (A/B) seçildi, motorlar ve FPS değerleri kesinleşti |
| **1: MVP** | OBS tarzı düzenleyici (kaynak = monitör, dondur akışı, çoklu dikdörtgen, [Test OCR]). Kısayol → OCR → Google çeviri → banner overlay + son satırlar paneli | Tam ekran bir oyunda kısayolla diyalog okunup overlay'de çevirisi görünüyor |
| **2: Oyun modu** | `oto` ve `bağlı` bölgeler, değişim algılama, tekrar filtresi. Yerinde overlay, profiller, tray, önbellek, satır geçmişi, DeepL | Diyalog ilerledikçe çeviri kendiliğinden beliriyor, CPU ve FPS hedefte |
| **3: 26.04 cilası** | GlobalShortcuts portalı, pencere kaynağı. Gerekirse GNOME Shell eklentisi (yöntem B). İsteğe bağlı X11 backend'i | 26.04'te kurulup sorunsuz çalışıyor |
| **4: Öğrenme + ekstralar** | Yerel web sayfası + Yomitan, Anki, LLM bağlamlı çeviri, çevrimdışı çeviri, [Öner] butonu, ek OCR motorları | Seçilenler tamam |
| **5: Paketleme** | Kurulum betiği / .deb / AppImage, ilk kurulum sihirbazı (kısayollar, model indirme) | Temiz bir Ubuntu'ya tek komutla kuruluyor |

**Test stratejisi:**
- Değişim algılama, oyunlardan kaydedilmiş kare dizileriyle birim testine tabi tutulur.
- OCR, örnek ekran görüntüleri ve beklenen metinlerle "altın" testlerle denetlenir.
- `tools/bench.py` her fazda CPU, RAM ve gecikmeyi ölçer.

## 12. Riskler

| Risk | Önlem |
|---|---|
| Wayland'da tam ekran oyunun üstünde overlay | Faz 0'da ilk iş test edilir. Yedekler: GNOME Shell eklentisi, kenarlıksız pencere, telefonda web sayfası |
| Ekran akışının oyun FPS'ine etkisi | Düşük FPS'te akış, oyun modu dışında akış kapalı, Faz 0'da ölçüm |
| GNOME sürüm farkları (46 → 50) | Kısayolda iki sürümde de çalışan CLI yolu, portal özellikleri sürüme göre açılır |
| Her tür oyunda farklı font ve stil | Bölge başına motor ve ön işleme, [Test OCR] ile hızlı ayar |
| JA/ZH → TR çeviri kalitesi | DeepL, gerekirse LLM bağlamlı çeviri, EN'yi yanında gösterme |
| Anahtarsız Google uç noktasının bozulması | Çevirmen arayüzü takılabilir, DeepL'e tek ayarla geçiş |

## 13. Hazır alternatifler

- **Interpreter** (bquenin/interpreter): JA → EN, meikiocr + Sugoi V4, overlay'li,
  çevrimdışı. Linux'ta X11/XWayland gerekir.
- **owocr**: çok motorlu OCR, ekran alanı seçimi.
- **GameSentenceMiner** (orijinal): Japonca öğrenimi ve Anki odaklı.

Bizim farkımız: OBS tarzı çoklu bölge düzenleyici, EN/JA/ZH kaynak + TR/EN hedef,
hafiflik öncelikli tasarım, Wayland'da yerel çalışma.

## 14. Faz 0 için senden gerekenler

1. **Ekran görüntüleri:** Her dilden (EN/JA/ZH) 5-10 tane, diyalog veya menü
   içeren. OCR karşılaştırması için.
2. **Test oyunları:** 2-3 oyun. Mümkünse biri Steam/Proton, biri yerel Linux, varsa
   bir emülatör. Overlay ve FPS testi için.
