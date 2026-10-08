# Oyun Ekranı OCR + Çeviri Aracı: Plan (Taslak v0.2)

## 0. Alınan kararlar

| Konu | Karar |
|---|---|
| Arayüz | **OBS Studio tarzı.** Kaynak (ekran/pencere) seçilir, oyun görüntüsü önizlemede görünür, metin alanları önizleme üstünde dikdörtgen olarak çizilir. Birden fazla bölge desteklenir |
| Oyun dilleri | Ağırlıklı İngilizce, Japonca, Çince |
| Çeviri hedefi | Türkçe ve İngilizce (profil başına seçilir, ikisi birden de gösterilebilir) |
| Oyun tarzı | Her tür oyun, genelde **tam ekran** |
| Dil öğrenme | İstenen ama sonraki aşama. Anki ilk aşamada yok, veri modeli şimdiden buna uygun tutulur (bkz. §9) |
| Platform | Ubuntu 24.04. Öneri: **"Ubuntu on Xorg" oturumuna geçmek** (gerekçesi §6'da) |

## 1. Hedef

Oyun oynarken ekrandaki metin alanlarını (diyalog kutusu, konuşan kişinin adı,
altyazı, menü) yakalayan, OCR ile okuyan ve anında çeviren bir masaüstü aracı.
En önemli kısıt: **hafif olmalı**, oyun oynarken bilgisayarı zorlamamalı.

## 2. Hafiflik ilkeleri

Programın neredeyse tüm maliyeti OCR'dan gelir. Bu yüzden asıl iş OCR'ı mümkün
olduğunca az çalıştırmak:

1. **Oyun sırasında tam ekran işlenmez.** Sadece çizilen bölgeler yakalanır.
2. **OCR sadece metin değişip sabitlendiğinde çalışır.** Değişim algılama çok ucuz
   (küçültülmüş gri görüntüde kare farkı, < 1 ms). Metin değişmiyorsa işlemci
   neredeyse hiç kullanılmaz.
3. **Daktilo efekti bitene kadar bekle.** Bölge K kare sabit kalınca tek bir OCR
   yapılır.
4. **GPU oyuna kalır.** OCR CPU'da, 1-2 thread ile, düşük öncelikte (`nice`)
   çalışır.
5. **Önizleme bedava değildir.** Canlı önizleme sadece düzenleyici penceresi
   görünürken çalışır (bkz. §3).
6. **Tekrar yok.** Benzer metin tekrar OCR'lanmaz veya çevrilmez, çeviriler
   SQLite'ta önbelleğe alınır.
7. **Birikme yok.** Kuyruklar tek elemanlı: OCR yetişemezse eski kare atılır.
8. **Tembel yükleme.** Modeller ilk ihtiyaçta yüklenir.

**Hedef bütçe** (Faz 0'da ölçülecek):

| Ölçüt | Hedef |
|---|---|
| Oyun sırasında, metin değişmiyorken CPU | tek çekirdeğin %1-2'si altı |
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
│ ( ) Ekran 2  │                                        │ ■ isim   bağlı   │
│ ( ) Pencere  │  ┌─ isim ──────┐                       │ ■ menü  kısayol  │
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
- **Ekran (monitör):** Tam ekran oyunlar için varsayılan ve en güvenilir kaynak.
  Oyun tam ekransa monitör görüntüsü zaten oyunun kendisidir.
- **Pencere:** Pencereli oyunlar için. X11'de koordinatlar pencereye göre tutulur,
  pencere taşınsa da bölgeler bozulmaz.

### 3.2 Bölgeler (birden fazla)
- Önizleme üstünde fareyle çizilir. Taşınabilir, köşelerinden boyutlandırılır,
  her biri adlandırılır ve renklendirilir.
- Koordinatlar kaynağa göre oransal (0-1) saklanır. Önizlemenin boyutu veya oyunun
  çözünürlüğü değişse de bölgeler doğru kalır.
- Her bölgenin bir **modu** vardır:

| Mod | Ne zaman | Örnek |
|---|---|---|
| `oto` | Bölge izlenir, metin değişip sabitlenince okunur | Diyalog kutusu, altyazı |
| `bağlı` | Kendisi izlenmez. Bağlı olduğu bölge tetiklenince onunla birlikte okunur | Konuşan kişinin adı (diyalogla birlikte) |
| `kısayol` | Sadece kısayola basınca okunur | Menü, eşya açıklaması |

- **[Test OCR]:** Seçili bölgeyi o anki karede hemen okur ve çevirir. Ayar yaparken
  sonucu anında görürsün.
- **[Öner]** (sonraki faz): O karede bir kez metin tespiti çalıştırır ve aday
  kutular önerir. Tek seferlik olduğu için oyun sırasında yük bindirmez.

### 3.3 Canlı ve dondurulmuş önizleme

| | Canlı | Dondur |
|---|---|---|
| Ne gösterir | Kaynağın akışını, 5-10 FPS, küçültülmüş | Tek bir kareyi, 1:1 netlikte |
| Maliyet | Sadece düzenleyici görünürken. Simge durumunda veya gizliyken 0 | Sıfır sürekli maliyet |
| İdeal kullanım | İki monitör: oyun birinde, düzenleyici diğerinde | Tek monitörde tam ekran oyun |

**Tek monitörde tam ekran oyunda bölge çizme akışı:**
1. Oyun açıkken kısayola basılır (ör. `Ctrl+Alt+E`) ve o anki kare dondurulur.
2. Düzenleyici açılır ve dondurulmuş kareyi gösterir.
3. Dikdörtgenler çizilir, [Test OCR] ile denenir, kaydedilir.
4. Oyuna dönülür. Bölgeler artık arka planda izleniyor.

Profil oyun başına bir kez hazırlanır, sonra sadece [Başlat] denir.

## 4. Çeviriyi gösterme (tam ekran öncelikli)

1. **Overlay (asıl yöntem):** Tam ekran oyunun üstünde duran, tıklamaları oyuna
   geçiren, yarı saydam bir kutu.
   - *Banner:* ekranın altında altyazı şeridi
   - *Yerinde:* ilgili bölgenin hemen altında veya üstünde
   - X11'de bunun için pencere yöneticisini atlayan (override-redirect),
     tıklamayı geçiren bir pencere kullanılır:
     `FramelessWindowHint | WindowStaysOnTopHint | X11BypassWindowManagerHint | WindowTransparentForInput`
   - Linux'ta Wine/Proton dahil "tam ekran" genelde ekranı kaplayan bir
     penceredir, bu yüzden overlay'in üstte görünmesi beklenir. **Faz 0'da senin
     makinende birkaç oyunla doğrulanacak.**
2. **Düzenleyicinin "son satırlar" paneli:** İki monitörde ideal.
3. **Pano (isteğe bağlı):** Sözlük araçlarıyla kullanmak için.

## 5. Mimari

**Teknoloji:** Python 3.12 (Ubuntu 24.04 varsayılanı) + PySide6 (Qt).
- Ağır işler native kütüphanelerde yapılır (ONNX Runtime, mss, Qt). Düşük FPS'te
  küçük bölgelerle Python'un ek yükü önemsizdir.
- OCR ekosisteminin tamamı Python'da.
- Qt düzenleyiciyi, overlay'i ve tray'i tek toolkit'le çözer.

```
 Düzenleyici (OBS tarzı) ──► Profil: kaynak + bölgeler + ayarlar
                                   │
                                   ▼
 Yakalama (sadece bölgeler) ─► Değişim algılama ─► Stabilite kapısı ─► OCR işçisi
                                                                          │
 Overlay / panel / pano ◄── Çevirmen (+önbellek) ◄── Tekrar filtresi ◄────┤
                                                                          ▼
                                                     Satır geçmişi (SQLite + kırpıntı)

 Tetikleyiciler: Tray · Global kısayol (X11) · CLI/IPC (Wayland'da GNOME kısayolu)
```

**Modül yapısı** (paket adı geçici):

```
src/gamesentenceminer/
  app.py              # giriş noktası, tray, ana döngü
  config.py           # ayarlar + oyun profilleri (TOML)
  capture/
    base.py           # CaptureBackend: list_sources(), grab(rect), grab_full()
    x11.py            # mss (XShm) ile yakalama
    wayland.py        # Portal ScreenCast + PipeWire (Faz 3)
  editor/
    window.py         # OBS tarzı ana pencere
    canvas.py         # önizleme + dikdörtgen çizme/taşıma/boyutlandırma
    suggest.py        # [Öner]: tek seferlik metin tespiti (Faz 4)
  pipeline/
    watcher.py        # değişim algılama + stabilite kapısı
    dedup.py          # benzer metin filtresi
    langdetect.py     # yazı sistemi tespiti: kana → ja, sadece Han → zh, Latin → en
  ocr/
    base.py  rapid.py  meiki.py  tesseract.py
  translate/
    base.py  deepl.py  google.py  llm.py  offline.py  cache.py
  overlay/
    banner.py  inplace.py
  store/
    history.py        # satır geçmişi (dil öğrenme için temel)
  ipc/
    server.py  cli.py # `gsm trigger`, `gsm freeze`, `gsm pause`
tests/
tools/
  bench.py            # makinende yakalama/OCR hızı ve CPU ölçümü
```

**Profil örneği** (`~/.config/gamesentenceminer/profiles/ornek-oyun.toml`):

```toml
[game]
name = "Örnek Oyun"
source = "monitor:1"            # monitor:N | window:<başlık eşleşmesi>

[ocr]
engine = "rapid"                # rapid | meiki | tesseract
source_lang = "auto"            # auto | en | ja | zh

[translate]
engine = "deepl"
target_langs = ["tr"]           # ["tr"], ["en"] veya ["tr", "en"]

[overlay]
style = "banner"                # banner | inplace | off

[[regions]]
name = "diyalog"
rect = [0.12, 0.72, 0.76, 0.20] # kaynağa göre oransal: x, y, genişlik, yükseklik
mode = "auto"                   # auto | linked | hotkey
fps = 3
stable_frames = 2
preprocess = ["scale2x", "grayscale"]

[[regions]]
name = "isim"
rect = [0.12, 0.66, 0.20, 0.05]
mode = "linked"
linked_to = "diyalog"
```

## 6. X11 mi, Wayland mı?

Kısaca: Ubuntu iki "görüntü sistemi" ile gelir. **Wayland** yeni ve varsayılan
olandır. **X11 (Xorg)** eski ama çok olgun olandır. Hangisinin kullanılacağı giriş
ekranında seçilir, kurulum veya veri değişikliği gerektirmez. İstenirse geri
dönülür.

### 6.1 Senin için X11'in artıları

1. **Bu araç için:** Ekran yakalama izinsiz ve en hızlı yolla çalışır. Global
   kısayollar ve tam ekran oyunun üstünde duran overlay doğrudan mümkündür.
   Wayland bunların üçünü de güvenlik gereği kısıtlar (GNOME 46'da uygulamalar
   global kısayol bile tanımlayamaz, bu özellik GNOME 48 ile geldi).
2. **ROS2 için:** RViz2 ve Gazebo (Harmonic) Wayland'da bilinen sorunlar yaşar.
   Genelde `QT_QPA_PLATFORM=xcb` gibi geçici çözümler gerekir, X11'de doğrudan
   çalışırlar.
3. **Oyun geliştirme / yapay zeka için:** Ekran kaydı, `xdotool` ile otomasyon ve
   editörlerin (Unity, Unreal) Linux'ta en çok test edildiği ortam X11. NVIDIA
   kartla X11 tarafı da daha oturmuş.
4. **Oyunlar için kayıp yok:** Steam/Proton oyunlarının çoğu Wayland'da bile X11
   uyumluluk katmanıyla (XWayland) çalışıyor.

### 6.2 Eksileri

1. **Çoklu monitörde karışık yenileme hızı** (ör. 144 Hz + 60 Hz) ve **kesirli
   ölçekleme** (%125, %150) Wayland'da daha iyi.
2. **Güvenlik:** X11'de her uygulama ekranı ve tuşları okuyabilir. Bizim aracın
   kolay olmasının sebebi de bu.
3. **Gelecek:** **Ubuntu 26.04 LTS'te GNOME'un Xorg oturumu kaldırıldı.** 24.04'te
   kaldığın sürece (destek 2029'a kadar) sorun yok. 26.04'e geçersen Wayland'a
   mecbur kalırsın.

### 6.3 Öneri

**24.04'te Xorg oturumuna geç.** ROS2 Jazzy de 24.04'e bağlı olduğu için bir süre
burada kalman muhtemel. Bu araç ve ROS2 için en sorunsuz ortam bu.

Ama aracı X11'e kilitlemiyoruz. Yakalama, kısayol ve overlay soyut arayüzlerin
arkasında olacak. Wayland desteği (Faz 3), 26.04'e geçmeden önce **zorunlu** olarak
eklenecek.

**Nasıl geçilir:**
1. Oturumu kapat.
2. Giriş ekranında kullanıcı adına tıkla.
3. Sağ alttaki çark (⚙) simgesinden **"Ubuntu on Xorg"**u seç.
4. Şifreni girip giriş yap. Seçim hatırlanır.
5. Kontrol: `echo $XDG_SESSION_TYPE` → `x11` yazmalı.

Çark simgesi görünmezse (bazı NVIDIA kurulumları) `/etc/gdm3/custom.conf`
ayarına bakılır. O durumda birlikte bakarız.

## 7. OCR motoru (EN / JA / ZH)

Motorlar takılıp çıkarılabilir (`OcrEngine` arayüzü), profil veya bölge başına
seçilir.

| Motor | Rolü | Neden |
|---|---|---|
| **RapidOCR (PP-OCRv5, ONNX)** | **Varsayılan, üç dil için** | Tek model Çince (basit + geleneksel), Japonca ve İngilizce okur. Çince'de alanının en iyilerinden. ONNX Runtime ile CPU'da hızlı, PyTorch gerekmez. İngilizce için ayrı bir PP-OCRv5 modeli de var |
| **meikiocr** | Japonca alternatif | Japon oyun metni ve piksel fontlar için eğitilmiş. Küçük modeller (tespit "tiny" ~30 ms CPU) |
| **Tesseract** | İngilizce, yedek | Çok hafif. Temiz fontlarda iyi, ön işleme ister |
| manga-ocr | İsteğe bağlı, ileride | Japoncada çok isabetli ama PyTorch ve ~1 GB+ RAM gerektirir |

- **Dil tespiti (`source_lang = "auto"`):** Metin kana içeriyorsa Japonca, sadece
  Han karakterleri varsa Çince, Latin harfleriyse İngilizce kabul edilir. Çevirmene
  doğru kaynak dil gönderilir.
- **Ön işleme** (bölge başına): 2x büyütme, gri ton, eşikleme veya ters çevirme
  (koyu zemin üzerinde açık yazı), metin rengine göre renk filtresi.
- Faz 0'da kendi oyunlarından alınmış EN/JA/ZH ekran görüntüleriyle motorlar
  karşılaştırılıp varsayılanlar kesinleştirilecek.

## 8. Çeviri (hedef: TR ve EN)

`Translator` arayüzü ile takılabilir:

- **DeepL API Free (varsayılan öneri):** Aylık 500k karakter, EN/JA/ZH → TR/EN
  destekli. Çeviri sunucuda yapıldığı için bilgisayara yük bindirmez. Hesap ve
  API anahtarı gerekir.
- **Google Translate:** DeepL anahtarı yoksa başlangıç seçeneği.
- **LLM API (Faz 4):** Bağlama duyarlı, oyunun tonunu koruyan çeviri. Önceki
  satırlar ve konuşan kişinin adı (`bağlı` bölgeden) bağlam olarak gönderilir.
- **Çevrimdışı (Faz 4):** Opus-MT veya NLLB-200 (CTranslate2, int8, CPU). Yerel
  LLM oyunla GPU/RAM için yarıştığı için varsayılan olmayacak.
- `target_langs = ["tr", "en"]` ile iki dil birden gösterilebilir. Dil öğrenirken
  işe yarar.
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

Böylece sonraki aşamada iki şey kolayca eklenir:

- **Yerel web sayfası:** Satırlar tarayıcıda akar ve Yomitan ile kelimelerin üstüne
  gelince sözlük açılır.
- **Anki:** Tek tuşla cümle + ekran görüntüsü + çeviriden kart oluşturulur.

## 10. Değişim algılama (hafifliğin kalbi)

Her `oto` bölge için, her tick'te (ör. 3 FPS):

1. Bölge yakalanır, 1/4 ölçeğe küçültülüp griye çevrilir.
2. Önceki kareyle ortalama mutlak fark hesaplanır.
3. Fark eşiğin üstündeyse bölge "değişiyor" sayılır. Fark eşiğin altına inip
   `stable_frames` boyunca öyle kalırsa OCR tetiklenir. Bu bölgeye `bağlı`
   bölgeler de aynı karede okunur.
4. Bölgede neredeyse hiç kenar yoksa (diyalog kutusu kapalı) OCR yapılmaz.
5. OCR sonucu öncekine çok benziyorsa (normalize Levenshtein > 0.9) çeviri
   atlanır.

Eşik ve kenar oranı, hareketli arka planlar için bölge başına ayarlanabilir.

## 11. Fazlar

| Faz | İçerik | Bitti sayılması için |
|---|---|---|
| **0: Keşif** | Xorg oturumuna geçiş. `mss` ile tam ekran oyun yakalama testi. **Tam ekran oyunun üstünde overlay testi.** EN/JA/ZH ekran görüntüleriyle OCR karşılaştırması (`tools/bench.py`). Çeviri servisi seçimi | Ölçümler elde, motorlar seçildi, overlay yöntemi doğrulandı |
| **1: MVP** | OBS tarzı düzenleyici: kaynak = monitör, canlı/dondur önizleme, çoklu dikdörtgen, [Test OCR]. Kısayol → OCR → çeviri. Sonuçlar "son satırlar" panelinde ve panoda | Bir oyunda bölge çizilip kısayolla okunup çevriliyor |
| **2: Oyun modu** | `oto` ve `bağlı` bölgeler, değişim algılama, tekrar filtresi. Overlay (banner + yerinde), profiller, tray, önbellek, satır geçmişi | Tam ekran oyunda diyalog ilerledikçe çeviri overlay'de kendiliğinden beliriyor, CPU hedefte |
| **3: Wayland** | Portal ScreenCast + PipeWire backend'i (bir kez izin, restore token), IPC + CLI ile GNOME kısayolu. Tam ekran üstü overlay için XWayland veya küçük bir GNOME Shell eklentisi değerlendirilir | Varsayılan Ubuntu oturumunda / 26.04'te çalışıyor |
| **4: Öğrenme + ekstralar** | Yerel web sayfası + Yomitan, Anki entegrasyonu, LLM bağlamlı çeviri, çevrimdışı çeviri, [Öner] butonu, ek OCR motorları | Seçilenler tamam |
| **5: Paketleme** | pipx / .deb / AppImage, ilk kurulum sihirbazı, model indirme | Temiz bir Ubuntu'ya tek komutla kuruluyor |

**Test stratejisi:**
- Değişim algılama, oyunlardan kaydedilmiş kare dizileriyle birim testine tabi tutulur.
- OCR, örnek ekran görüntüleri ve beklenen metinlerle "altın" testlerle denetlenir.
- `tools/bench.py` her fazda CPU, RAM ve gecikmeyi ölçer.

## 12. Riskler

| Risk | Önlem |
|---|---|
| Tam ekran oyunda overlay'in görünmemesi | Faz 0'da erken test. Yedekler: kenarlıksız pencere modu, ikinci monitörde panel |
| Ubuntu 26.04'te Xorg'un olmaması | Soyut backend'ler, Faz 3 zorunlu |
| Her tür oyunda farklı font ve stil | Bölge başına motor ve ön işleme, [Test OCR] ile hızlı ayar |
| JA/ZH → TR çeviri kalitesi | DeepL, gerekirse LLM bağlamlı çeviri, EN'yi yanında gösterme |
| Hareketli arka planda yanlış tetik | Eşik, stabilite ve kenar oranı ayarları |

## 13. Hazır alternatifler

- **Interpreter** (bquenin/interpreter): JA → EN, meikiocr + Sugoi V4, overlay'li,
  çevrimdışı. Linux'ta X11/XWayland gerekir.
- **owocr**: çok motorlu OCR, ekran alanı seçimi.
- **GameSentenceMiner** (orijinal): Japonca öğrenimi ve Anki odaklı.

Bizim farkımız: OBS tarzı çoklu bölge düzenleyici, EN/JA/ZH kaynak + TR/EN hedef,
hafiflik öncelikli tasarım, Wayland'a hazır mimari.

## 14. Açık sorular

1. **Kaç monitör?** Tek monitörse "dondur" akışı, iki monitörse canlı önizleme
   öncelikli tasarlanır.
2. **Ekran kartı?** NVIDIA / AMD / Intel ve (NVIDIA ise) sürücü sürümü.
3. **Xorg'a geçtikten sonra** `echo $XDG_SESSION_TYPE` çıktısı `x11` mi?
4. **DeepL API Free anahtarı alabilir misin?** Olmazsa MVP'ye Google Translate ile
   başlanır.
