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

1. Araç çubuğunun solundan kaynağı seç:
   - **Oyun penceresi** (önerilen): Sadece oyun yakalanır. Önizlemede masaüstü,
     overlay ya da bu uygulama görünmez. Bölgeler oyun penceresine göre konumlanır.
   - **Tüm ekran:** Monitörün tamamı yakalanır.
2. **Yakalamayı başlat**'a bas. İlk seferde GNOME'un paylaşım penceresi açılır.
   **Pencere** sekmesinden oyunu (ya da monitörünü) seç. **"Bu seçimi anımsa"**
   işaretli kalsın, **Paylaş**'a bas. Sonraki açılışlarda bir daha sormaz. Başka
   bir oyun seçmek için **Kaynağı yeniden seç**'e bas.
3. Önizlemede diyalog kutusunun üstüne fareyle **dikdörtgen çiz**. İstediğin kadar
   bölge çizebilirsin.
   - Taşımak için sürükle.
   - Boyutlandırmak için sağ alt köşeden tut.
   - Silmek için Delete'e bas.
   - Yeniden adlandırmak için listede çift tıkla.
   Pencere ve tüm ekran modlarının bölgeleri ayrı saklanır.
4. **Oku**'ya bas: Okunan metin ve çevirisi alttaki panelde görünür.
5. **Otomatik oku** açıkken oyuna dön. "Otomatik" moddaki bölgelerde metin değişip
   durduğunda kendiliğinden okunur.
6. **Overlay üstte / altta** seçersen çeviri oyunun üstünde şerit olarak görünür.
   - Şerit tıklamaları oyuna geçirir.
   - Yüksekliği metne göre ayarlanır. Uzun metinde yazı küçülür, gerekirse
     orijinal satır gizlenir.
   - ⚙ menüsünden orijinal metni tamamen kapatabilirsin.

Oyundan uygulamaya dönünce, ayrılmadan hemen önceki oyun karesi donmuş olarak
gösterilir. Böylece tek monitörde de bölge çizebilirsin. ⚙ menüsünden
kapatılabilir. Alternatif: **3 sn sonra dondur**.

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
