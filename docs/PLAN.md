# Oyun Ekranı OCR + Çeviri Aracı: Plan (Taslak v0.1)

> Durum: taslak. "Açık kararlar" bölümündeki sorular cevaplanınca güncellenecek.

## 1. Hedef

Oyun oynarken ekrandaki belirli metin alanlarını (diyalog kutusu, altyazı, menü,
eşya açıklaması) yakalayan, OCR ile okuyan ve anında çeviren bir masaüstü aracı.

- Platform: Ubuntu 24.04 (GNOME 46)
- En önemli kısıt: **hafif olmalı**, oyun oynarken bilgisayarı zorlamamalı.

## 2. Hafiflik ilkeleri

Programın neredeyse tüm maliyeti OCR'dan gelir. Bu yüzden asıl iş OCR'ı mümkün
olduğunca az çalıştırmak:

1. **Tam ekranı asla sürekli OCR'lama.** Sadece seçili küçük bölgeler yakalanır.
2. **OCR sadece metin değişip sabitlendiğinde çalışır.** Değişim algılama çok
   ucuz (küçültülmüş gri görüntüde kare farkı, < 1 ms). Metin değişmiyorsa
   işlemci neredeyse hiç kullanılmaz.
3. **Daktilo efekti bitene kadar bekle.** Bölge K kare boyunca sabit kalınca tek
   bir OCR yapılır; harf harf beliren metin için 10 kez OCR yapılmaz.
4. **GPU oyuna kalır.** OCR varsayılan olarak CPU'da, 1-2 thread ile ve düşük
   öncelikte (`nice`) çalışır. Küçük kırpılmış görüntülerde CPU yeterince hızlı.
5. **Tekrar yok.** Aynı/çok benzer metin tekrar OCR'lanmaz veya çevrilmez,
   çeviriler SQLite'ta önbelleğe alınır.
6. **Birikme yok.** Kuyruklar tek elemanlı: OCR yetişemezse eski kare atılır.
7. **Tembel yükleme.** Modeller ilk ihtiyaçta yüklenir, kullanılmayan motor RAM
   tutmaz.

**Hedef bütçe** (Faz 0'da makinende ölçülecek):

| Ölçüt | Hedef |
|---|---|
| Boşta CPU (metin değişmiyorken) | tek çekirdeğin %1-2'si altı |
| RAM | ~300-400 MB altı (ağır motor seçilmezse) |
| Metin değişiminden çeviri görünene kadar | ~1 sn altı |

## 3. Çalışma modları

| Mod | Ne yapar | Arka plan yükü |
|---|---|---|
| **Kısayol** | Tuşa bas, kayıtlı bölge(ler) bir kez okunup çevrilir | Sıfır |
| **Otomatik izleme** | Bölgeler 2-4 FPS izlenir, metin değişince OCR + çeviri | Çok düşük |
| **Serbest seçim** | Kısayolla ekranda dikdörtgen çiz, o alan bir kez okunur | Sıfır |

Otomatik izleme diyalog kutuları için, serbest seçim ise menüler ve tek seferlik
yazılar için kullanılır.

## 4. Metin alanı seçimi

Öneri: **manuel seçim temel yöntem olsun, otomatik tespit sadece yardımcı olsun.**

- **Manuel seçim:** Yarı saydam tam ekran katmanda fareyle dikdörtgen çizilir.
  Birden fazla bölge olabilir, her birine ad verilir ("diyalog", "konuşan kişi").
  Her bölgenin kendi ayarı olur: mod, FPS, ön işleme.
- **Otomatik öneri (tek seferlik):** Bir tuşla tam ekranda bir kez *metin
  tespiti* çalışır. Bulunan kutular ekranda gösterilir, tıklayarak kabul edip
  boyutlarını ayarlarsın. Sadece kurulum sırasında çalıştığı için oyun sırasında
  yük bindirmez.
- **Sürekli tam otomatik bölge bulma önerilmez.** Hem pahalı hem de HUD, sayı ve
  arayüz yazıları yüzünden çok yanlış alarm verir.
- Bölgeler **oyun profiline** kaydedilir. X11'de koordinatlar oyun penceresine
  göre oransal tutulur, böylece pencere taşınınca veya çözünürlük değişince bölgeler
  bozulmaz.

## 5. Ubuntu 24.04'teki kritik konu: Wayland ve X11

Ubuntu 24.04 varsayılan olarak **GNOME 46 + Wayland** ile gelir. Wayland güvenlik
gereği ekran yakalamayı, global kısayolları ve "her zaman üstte" pencereleri
kısıtlar. Tasarımı en çok bu konu etkiler.

| Konu | X11 ("Ubuntu on Xorg" oturumu) | Wayland (varsayılan) |
|---|---|---|
| Ekran yakalama | `mss` (XShm) ile çok hızlı, izin gerekmez | XDG Portal ScreenCast + PipeWire. Bir kez izin istenir, izin hatırlanabilir (restore token) |
| Global kısayol | Doğrudan (XGrabKey) | GNOME 46'da uygulamalar global kısayol tanımlayamaz (GlobalShortcuts portalı GNOME 48 ile geldi). Çözüm: GNOME Ayarlar'da özel kısayol tanımlanır ve bizim CLI komutunu çağırır, komut da IPC ile çalışan uygulamaya iletir |
| Üstte duran, tıklamayı geçiren overlay | Kolay | Uygulama XWayland ile (`QT_QPA_PLATFORM=xcb`) çalıştırılır. Tam ekran oyunda görünmeyebilir, bu yüzden "kenarlıksız pencere" modu önerilir |
| Aktif pencere / pencere konumu | Okunabilir, profil otomatik seçilir | Okunamaz. Mutlak ekran koordinatları kullanılır, profil elle seçilir |

**Öneri:**
- MVP **X11 yolu** üzerine kurulur: en hızlı geliştirilen ve en hafif yol bu.
- Ekran yakalama soyut bir `CaptureBackend` arayüzünün arkasında olur. Wayland
  desteği sonraki fazda ayrı bir backend olarak eklenir, mimari değişmez.
- Steam/Proton oyunlarının çoğu Wayland oturumunda da XWayland üzerinden çalışır.
  Bu yüzden X11 yakalama yolu bazı oyunlarda Wayland'da da çalışabilir, ama garanti
  değil. Faz 0'da senin makinende test edilecek.

Oturum tipini görmek için: `echo $XDG_SESSION_TYPE`

## 6. OCR motoru (oyunun diline bağlı)

Motorlar takılıp çıkarılabilir (`OcrEngine` arayüzü), her profilde ayrı seçilir.

| Motor | Dil | Artı | Eksi |
|---|---|---|---|
| **meikiocr** | Japonca | Oyun metni için eğitilmiş, yerel, küçük modeller (tespit "tiny" ~30 ms CPU) | Genç proje, CPU'daki tanıma hızı ölçülmeli |
| **RapidOCR (PP-OCRv5, ONNX)** | Çince/Japonca/İngilizce tek model, başka diller | ONNX Runtime, CPU'da hızlı, PyTorch gerekmez | Stilize fontlarda meikiocr'dan zayıf olabilir |
| **Tesseract** | İngilizce/Latin | Çok hafif, apt ile kurulur | Ön işleme ister, Japoncada zayıf |
| **manga-ocr** | Japonca | Çok isabetli | PyTorch, ~1 GB+ RAM, hafiflik hedefiyle çelişir |
| Google Lens (çevrimiçi) | Çoğu dil | Çok isabetli, yerel yük yok | İnternet, gecikme, resmi olmayan API |

**Ön işleme** (profil başına): 2x büyütme, gri ton, gerekirse eşikleme veya ters
çevirme (koyu zemin üzerinde açık yazı), metin rengine göre renk filtresi.

## 7. Çeviri

`Translator` arayüzü ile takılabilir:

- **Çevrimiçi** (bilgisayara sıfır yük, hafiflik açısından en iyisi):
  - DeepL API Free: aylık 500k karakter, JA/EN → TR destekli. Varsayılan önerim bu.
  - Google Translate
  - LLM API: bağlama duyarlı ve oyunun tonunu koruyan çeviri. Önceki birkaç satır
    ve karakter isimleri bağlam olarak gönderilebilir.
- **Çevrimdışı:**
  - Argos Translate / Opus-MT / NLLB-200 (CTranslate2, int8, CPU). Doğrudan
    JA→TR modelleri zayıf olduğu için genelde JA→EN→TR pivotu gerekir.
  - Yerel LLM (llama.cpp/Ollama): kaliteli, ama GPU ve RAM için oyunla yarışır.
    "Hafif" hedefiyle çeliştiği için varsayılan olmayacak.
- **Önbellek + geçmiş:** SQLite'ta tutulur (orijinal metin, çeviri, oyun, zaman).

## 8. Gösterim

- **Overlay:** Oyunun üstünde duran, tıklamaları oyuna geçiren yarı saydam kutu.
  - *Banner:* ekranın altında altyazı şeridi
  - *Yerinde:* ilgili bölgenin hemen altında veya üstünde
- **Panel penceresi:** Orijinal metin, çeviri ve geçmiş. İkinci monitör için ideal,
  oyuna hiç dokunmaz.
- **Pano (isteğe bağlı):** Metni panoya kopyalar, Yomitan gibi sözlük araçlarıyla
  birlikte kullanılabilir.
- **Tray ikonu:** duraklat/devam, profil seç, bölge düzenle, mod değiştir.

## 9. Mimari

**Teknoloji:** Python 3.12 (Ubuntu 24.04 varsayılanı) + PySide6 (Qt).
- Python'un yükü sorun değil: ağır işler native kütüphanelerde (ONNX Runtime,
  mss, Qt) yapılır, düşük FPS'te küçük bölgelerle Python ek yükü önemsizdir.
- OCR ekosisteminin tamamı Python'da.
- Qt şeffaf overlay, tray, seçim katmanı ve paneli tek toolkit'le çözer.

```
             ┌──────────── Profil / Bölgeler ◄──── Bölge seçici (manuel / öneri)
             ▼
 Yakalama (bölge, N FPS) ─► Değişim algılama ─► Stabilite kapısı ─► OCR işçisi
                                                                       │
 UI (overlay / panel / pano) ◄── Çevirmen (+önbellek) ◄── Tekrar filtresi ◄┘

 Tetikleyiciler: Tray · Kısayol (X11) · CLI/IPC (Wayland'da GNOME kısayolu)
```

**Modül yapısı** (paket adı geçici):

```
src/gamesentenceminer/
  app.py              # giriş noktası, tray, ana döngü
  config.py           # ayarlar + oyun profilleri (TOML)
  capture/
    base.py           # CaptureBackend arayüzü
    x11.py            # mss ile yakalama
    wayland.py        # Portal ScreenCast + PipeWire (Faz 3)
  regions/
    selector.py       # dikdörtgen çizme katmanı
    suggest.py        # tek seferlik metin tespiti ile öneri (Faz 4)
  pipeline/
    watcher.py        # değişim algılama + stabilite kapısı
    dedup.py          # benzer metin filtresi
  ocr/
    base.py  meiki.py  rapid.py  tesseract.py
  translate/
    base.py  deepl.py  google.py  llm.py  offline.py  cache.py
  ui/
    overlay.py  panel.py  tray.py
  ipc/
    server.py  cli.py # `gsm trigger`, `gsm select`, `gsm pause`
tests/
tools/
  bench.py            # makinende yakalama/OCR hızı ve CPU ölçümü
```

**Profil örneği** (`~/.config/gamesentenceminer/profiles/ornek-oyun.toml`):

```toml
[game]
name = "Örnek Oyun"
match_window = "OrnekOyun"      # X11'de pencere başlığından otomatik profil seçimi

[ocr]
engine = "meiki"
source_lang = "ja"
preprocess = ["scale2x", "grayscale"]

[translate]
engine = "deepl"
target_lang = "tr"

[[regions]]
name = "diyalog"
rect = [0.12, 0.72, 0.76, 0.20]  # pencereye göre oransal: x, y, genişlik, yükseklik
mode = "auto"                    # auto | hotkey
fps = 3
stable_frames = 2
```

## 10. Değişim algılama (hafifliğin kalbi)

Her tick'te (ör. 3 FPS):

1. Bölge yakalanır, 1/4 ölçeğe küçültülüp griye çevrilir.
2. Önceki kareyle ortalama mutlak fark hesaplanır.
3. Fark eşiğin üstündeyse bölge "değişiyor" sayılır. Fark eşiğin altına inip
   `stable_frames` boyunca öyle kalırsa OCR tetiklenir.
4. Bölgede neredeyse hiç kenar yoksa (diyalog kutusu kapalı) OCR yapılmaz.
5. OCR sonucu bir öncekine çok benziyorsa (normalize Levenshtein > 0.9) çeviri
   atlanır.

Hareketli arka plan üzerindeki yazılar için eşik ve kenar oranı profil başına
ayarlanabilir.

## 11. Fazlar

| Faz | İçerik | Bitti sayılması için |
|---|---|---|
| **0: Keşif** | Açık kararlar. Makine testi (oturum tipi, CPU/GPU). Oyunlarından örnek ekran görüntüleriyle OCR motorlarını karşılaştırma (`tools/bench.py`). X11 yakalamanın senin Wayland oturumunda çalışıp çalışmadığı | Motor ve çevirmen seçildi, ölçümler elde |
| **1: MVP** | X11 yakalama, manuel bölge seçimi, kısayol → OCR → çeviri → basit panel + pano. Tek OCR motoru, tek çevirmen | Bir oyunda kısayolla diyalog okunup çevriliyor |
| **2: Otomatik izleme** | Değişim algılama, stabilite, tekrar filtresi. Overlay (banner + yerinde), oyun profilleri, tray, önbellek, geçmiş | Diyalog ilerledikçe çeviri kendiliğinden geliyor, boşta CPU hedefte |
| **3: Wayland** | Portal ScreenCast + PipeWire backend'i, IPC + CLI, GNOME kısayolu kurulum yardımcısı | Varsayılan Ubuntu oturumunda çalışıyor |
| **4: Ekstralar** | Otomatik bölge önerisi, çevrimdışı çeviri, ek OCR motorları, bağlamlı LLM çevirisi, WebSocket/Anki entegrasyonu | Seçilenler tamam |
| **5: Paketleme** | pipx / .deb / AppImage, ilk kurulum sihirbazı, model indirme | Temiz bir Ubuntu'ya tek komutla kuruluyor |

**Test stratejisi:**
- Değişim algılama, oyunlardan kaydedilmiş kare dizileriyle birim testine tabi tutulur.
- OCR, örnek ekran görüntüleri ve beklenen metinlerle "altın" testlerle denetlenir.
- `tools/bench.py` her fazda CPU, RAM ve gecikmeyi ölçer.

## 12. Riskler

| Risk | Önlem |
|---|---|
| Wayland kısıtları | X11 ile başla, Wayland'ı ayrı backend olarak ekle, Xorg oturumu alternatif |
| Tam ekran (exclusive) oyunda overlay görünmemesi | Kenarlıksız pencere modu, ikinci monitörde panel |
| Piksel/stilize fontlarda OCR hataları | Profil başına motor seçimi ve ön işleme |
| JA→TR çeviri kalitesi | LLM çevirmeni veya EN pivotu |
| Hareketli arka planda yanlış tetik | Eşik, stabilite ve kenar oranı ayarları |

## 13. Hazır alternatifler

Benzer işi yapan açık kaynak araçlar var. Denemek, bizim aracın neyi farklı
yapması gerektiğini netleştirir:

- **Interpreter** (bquenin/interpreter): Japonca oyun metnini meikiocr ile okuyup
  Sugoi V4 ile İngilizceye çeviriyor. Overlay'li ve çevrimdışı çalışıyor. Linux'ta
  X11/XWayland gerektiriyor. Hedef dil İngilizce.
- **owocr**: çok motorlu OCR aracı, ekran alanı seçimi ve tray menüsü var.
- **GameSentenceMiner** (orijinal): Japonca öğrenimi ve Anki odaklı.

Olası farkımız: Türkçe hedef dil, hafiflik öncelikli tasarım, Wayland desteği.

## 14. Açık kararlar

1. Oyunlar hangi dilde? (Japonca / İngilizce / karışık) → OCR motorunu belirler
2. Hedef dil Türkçe mi? Çevrimiçi çeviri (DeepL/Google/LLM) kabul mü, yoksa
   tamamen çevrimdışı mı olmalı?
3. `echo $XDG_SESSION_TYPE` çıktısı ne? Oyun için Xorg oturumuna geçmek sorun olur mu?
4. Donanım: CPU, RAM, GPU (NVIDIA/AMD)? Tek monitör mü, iki mi?
5. Oyunları nasıl oynuyorsun: Steam/Proton, emülatör, yerel Linux? Tam ekran mı,
   pencereli mi?
6. Amaç sadece çeviri mi, yoksa dil öğrenme de mi (sözlük, Anki)? Repo adı
   ("sentence miner") ikincisini düşündürüyor.

**Cevap gelmezse varsayılanlar:** Python + PySide6, önce X11, Japonca için
meikiocr / diğer diller için RapidOCR, DeepL Free, manuel bölge + otomatik izleme.
