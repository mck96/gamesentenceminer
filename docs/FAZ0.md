# Faz 0: Teknik denemeler

Amaç: Plandaki iki büyük belirsizliği senin bilgisayarında ölçmek.

1. **Ekran yakalama:** OBS'un kullandığı portal + PipeWire yolu çalışıyor mu, izin
   hatırlanıyor mu, oyunun FPS'ine maliyeti ne?
2. **Overlay:** Çeviri şeridi tam ekran oyunun üstünde görünüyor mu, tıklamalar
   oyuna geçiyor mu?

Toplam süre yaklaşık 20-30 dakika. Bir oyun açık olacak.

## Senin makinendeki sonuçlar

### Ortam ve ilk yakalama (8 Ekim)

**Ortam:**
- Ubuntu 24.04.5, GNOME 46.0, **X11 oturumu**.
- RTX 4070 SUPER (sürücü 580), 2560x1440 @ 144 Hz.
- ScreenCast portalı sürüm 5, GlobalShortcuts portalı yok (beklenen).

**Yakalama (masaüstünde, oyunsuz):**

| Ölçüt | Sonuç |
|---|---|
| Portal + PipeWire | Çalıştı |
| Düşük FPS isteği (`max-framerate`) | **Kabul edildi**: GNOME saniyede en fazla 5 kare gönderiyor. Sabit masaüstünde ortalama 2,7, çünkü sadece ekran değişince kare geliyor |
| Bizim işlemci kullanımımız | %0,7 (tek çekirdeğin), RAM 113 MB |
| gnome-shell işlemci kullanımı | Akış açıkken %5,3. Akışsız baz değer henüz ölçülmedi (2c) |
| Örnek kare | Siyah değil (ortalama parlaklık 68) |

**İzin hatırlanmadı.** GNOME kaynak koduna göre bunun tek nedeni, paylaşım
penceresindeki **"Bu seçimi anımsa"** kutusunun işaretsiz olması. Kutu varsayılan
olarak işaretli gelir. İşaretliyken GNOME geri yükleme verisini döndürür, portal da
bunu anahtara çevirir.

**Overlay testi çalışmadı:** Betik `uv run` yerine `python3` ile başlatıldı.
`python3` sistem Python'unu kullanır ve orada PySide6 yok.

### Kalan testler

Kalan testler 2b, 2c ve 3. Hepsini `uv run ...` ile çalıştır. Kısayol olarak artık
uygulamanın kendisiyle de denenebilir: `uv run gsm`, overlay'i "üstte" seç, oyuna geç.

## Kurulum

```bash
git clone https://github.com/mck96/gamesentenceminer.git
cd gamesentenceminer
git checkout claude/jolly-tesla-6ln394
./scripts/setup_ubuntu.sh
```

Betik `sudo` ile birkaç sistem paketi kurar (GStreamer'ın PipeWire eklentisi,
derleme araçları, Qt'nin X11 kütüphaneleri). `uv` yoksa onu da kurar, sonra proje
ortamını hazırlar. İlk seferde PyGObject derlendiği için bir dakika kadar sürer.

## 1. Ortam kontrolü (1 dk)

```bash
python3 tools/spikes/check_env.py
```

Çıktının tamamını gönder.

## 2. Ekran yakalama (10 dk)

### 2a. İzni ver (oyun kapalıyken)

```bash
uv run tools/spikes/capture_portal.py --duration 10
```

- GNOME'un "Ekran paylaşımı" penceresi açılır. Monitörünü seçip **Paylaş**'a bas.
  Pencerede "hatırla" gibi bir seçenek varsa işaretle.
- Üst çubukta ekran paylaşımı simgesi belirir, 10 saniye sonra kaybolur.
- `spike_out/capture_sample.png` dosyasını aç. Ekranının görüntüsü mü, yoksa
  siyah mı?

### 2b. İzin hatırlanıyor mu?

Aynı komutu tekrar çalıştır. Bu sefer **pencere açılmamalı**. Özette
`token reused` yazmalı.

### 2c. Oyunla maliyet ölçümü

1. FPS sayacını aç. Steam'de: **Ayarlar → Oyun içi → Oyun içi FPS sayacı**. Steam
   dışı oyunlar için MangoHud kullanılabilir.
2. Oyunu tam ekran aç ve hareketin az olduğu sabit bir sahnede dur. Sahne sabit
   olmazsa FPS zaten dalgalanır ve fark ölçülemez.
3. Alt+Tab ile terminale geç ve çalıştır:

   ```bash
   uv run tools/spikes/capture_portal.py --delay 10 --baseline 20 --duration 40
   ```

4. 10 saniye içinde oyuna dön. Zil sesleri:
   - **1. zil:** Baz ölçüm başladı. Ekran akışı kapalı, 20 saniye sürer.
   - **2. zil:** Ekran akışı açıldı, 40 saniye sürer.
   - **3. zil:** Bitti.
5. Her iki aşamadaki oyun FPS'ini not et.

İstersen aynı denemeyi `--no-max-fps` ekleyerek bir kez daha yap. Bu, GNOME'a
"bana daha az kare gönder" dememenin maliyetini gösterir.

## 3. Overlay (10 dk)

1. **Oyun kapalıyken:**

   ```bash
   uv run tools/spikes/overlay_test.py
   ```

   Ekranın altında yarı saydam bir şerit çıkmalı: üstte küçük bilgi satırı, sağda
   dönen bir sayaç, ortada Japonca, Çince ve Türkçe örnek satırlar.
2. Şeridin üstüne tıkla. Tıklama alttaki pencereye geçmeli.
3. Terminal açık kalsın. Oyunu tam ekran aç ya da Alt+Tab ile ona geç. Şu üç şeye
   bak:
   - Şerit oyunun üstünde görünüyor mu?
   - Sayaç ilerliyor mu?
   - Şeridin üstüne tıklayınca oyun tıklamayı alıyor mu?
4. Kapatmak için Alt+Tab ile terminale dön ve **Ctrl+C**'ye bas.
5. Şerit oyunun üstünde görünmediyse sırayla şunları dene:

   ```bash
   uv run tools/spikes/overlay_test.py --mode ontop
   uv run tools/spikes/overlay_test.py --platform wayland   # çalışmaması bekleniyor, karşılaştırma için
   ```

Mümkünse 2-3 farklı oyunla dene: biri Steam/Proton, biri yerel Linux oyunu, varsa
bir emülatör.

## Ne göndereceksin

1. `check_env.py` çıktısı
2. 2a ve 2c'nin terminal özeti (`== capture spike summary ==` kısmı) ya da
   `spike_out/capture_report.json`
3. 2c'deki iki FPS değeri, oyunun adı ve nasıl çalıştığı (Proton / yerel / emülatör)
4. 2b'de izin penceresi tekrar açıldı mı?
5. Overlay sonuçları, şu tabloyla:

   | Oyun | Proton / yerel | `bypass` (varsayılan) üstte mi? | `ontop` üstte mi? | Tıklama oyuna geçti mi? | FPS değişti mi? |
   |---|---|---|---|---|---|

`capture_sample.png` ekranında o an ne varsa içerir. Göndermek isteğe bağlı,
siyah olup olmadığını söylemen yeterli.

## Bulut ortamında doğrulananlar

Bulut geliştirme ortamında GNOME yok. Bu yüzden gerçek bir PipeWire sunucusu ve
WirePlumber üstünde, 60 FPS'lik bir test video düğümüne karşı sahte bir portalla
(`tools/dev/mock_screencast_portal.py`) uçtan uca denendi:

- **Portal akışı:** `CreateSession` → `SelectSources` → `Start` →
  `OpenPipeWireRemote` istek/yanıt sinyalleri ve fd aktarımı çalışıyor. Oturum
  çıkışta kapanıyor.
- **İzin anahtarı:** Restore token kaydediliyor ve sonraki çalıştırmada
  `SelectSources`'a geri gönderiliyor.
- **Bağlantı ve renk:** `pipewiresrc` portalın verdiği fd ve düğüm kimliğiyle
  bağlanıyor. `max-framerate=5/1` kısıtlaması kabul ediliyor. 60 FPS gelen akıştan
  saniyede ~5 kare tutuluyor. Örnek karede renk sırası doğru.
- **Uygulama notu:** `pipewiresrc` bir biçim kısıtlaması olmadan (her biçimi kabul
  eden `fakesink` gibi) bağlanamadı. Gerçek kodda akışın önüne her zaman bir
  `video/x-raw` kısıtlaması konacak.
- **Açık gözlem:** Aynı sahte portal sürecinden art arda ikinci bir oturum
  açıldığında kaynak hızı düştü (60 yerine ~3-5 FPS). Temiz ortamda ikinci
  çalıştırma tek başına 60 FPS aldı. Aynı kaynağa bağlanan düz GStreamer
  tüketicileri de art arda sorunsuz çalıştı. Bu, test düzeneğine özgü görünüyor:
  gerçek GNOME her portal oturumunda yeni bir akış düğümü açıyor. Yine de 2b/2c'deki
  `source=…fps` değerleriyle doğrulanacak.
- **Overlay:** Betik X11 üzerinden hatasız açılıyor, Japonca/Çince/Türkçe yazılar
  doğru çiziliyor. Saydamlık ve "oyunun üstünde kalma" ancak GNOME'da test edilebilir.
