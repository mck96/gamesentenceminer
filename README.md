# gamesentenceminer

Oyun ekranındaki metin alanlarını (diyalog kutusu, altyazı, menü) OCR ile okuyup
anında çeviren hafif bir Linux aracı. Hedef platform GNOME (Ubuntu 24.04 / 26.04,
X11 veya Wayland).

**Durum:** İlk çalışan sürüm (Faz 1 MVP). Geliştirme sürüyor.

- Plan: [docs/PLAN.md](docs/PLAN.md)
- Teknik denemeler ve ölçümler: [docs/FAZ0.md](docs/FAZ0.md)

## Kurulum

```bash
./scripts/setup_ubuntu.sh
```

Betik şunları yapar:
- Sistem paketlerini kurar: GStreamer PipeWire eklentisi, PyGObject derleme
  bağımlılıkları, Qt X11 kütüphaneleri.
- Sonra [uv](https://docs.astral.sh/uv/) ile proje ortamını hazırlar. Python
  sistemden bağımsız, uv'nin yönettiği 3.12 sürümüdür.

## Kullanım

```bash
uv run gsm
```

1. **Yakalamayı başlat**'a bas. İlk seferde GNOME'un ekran paylaşım penceresi
   açılır. Monitörünü seç, **"Bu seçimi anımsa"** işaretli kalsın, **Paylaş**'a bas.
   Sonraki açılışlarda bir daha sormaz.
2. Oyuna geç (Alt+Tab), diyalog ekrandayken uygulamaya geri dön. **Dönünce dondur**
   açıksa, ayrılmadan hemen önceki oyun karesi önizlemede donmuş olarak görünür.
   Alternatif: **3 sn sonra dondur**'a basıp 3 saniye içinde oyuna geç.
3. Önizlemede diyalog kutusunun üstüne fareyle **dikdörtgen çiz**. İstediğin kadar
   bölge çizebilirsin.
   - Taşımak için sürükle.
   - Boyutlandırmak için sağ alt köşeden tut.
   - Silmek için Delete'e bas.
   - Yeniden adlandırmak için listede çift tıkla.
4. **Oku**'ya bas: Okunan metin ve çevirisi alttaki panelde görünür.
5. **Otomatik oku** açıkken oyuna dön. "Otomatik" moddaki bölgelerde metin değişip
   durduğunda kendiliğinden okunur.
6. **Overlay üstte / altta** seçersen çeviri oyunun üstünde şerit olarak görünür.
   Şerit tıklamaları oyuna geçirir. Şerit bölgenin üstüne gelse bile OCR onu görmez.

Bölgeler ve ayarlar `~/.config/gamesentenceminer/settings.json` dosyasında saklanır.
Durum çubuğunda uygulamanın işlemci kullanımı, kare hızı ve son OCR süresi görünür.

## Geliştirme

```bash
uv run pytest                 # birim testleri
uv run ruff check src tests tools
uv run gsm --fake-source a.png,b.png   # ekran yerine görselleri oynatır
```

## Dizin yapısı

| Yol | İçerik |
|---|---|
| `src/gamesentenceminer/capture/` | Portal + PipeWire ile ekran yakalama |
| `src/gamesentenceminer/ocr/` | RapidOCR (PP-OCRv6) sarmalayıcısı |
| `src/gamesentenceminer/translate/` | Çevirmen (şimdilik anahtarsız Google) |
| `src/gamesentenceminer/pipeline/` | Değişim algılama, metin yardımcıları, okuma hattı |
| `src/gamesentenceminer/editor/` | OBS tarzı pencere ve önizleme tuvali |
| `src/gamesentenceminer/overlay.py` | Oyunun üstündeki çeviri şeridi |
| `tools/spikes/` | Faz 0 deneme betikleri |
| `tools/dev/` | Geliştirme araçları, ör. sahte ScreenCast portalı |
| `tests/` | Birim testleri |
