# gamesentenceminer

Oyun ekranındaki metin alanlarını (diyalog kutusu, altyazı, menü) OCR ile okuyup
anında çeviren hafif bir Linux aracı. Hedef platform GNOME + Wayland (Ubuntu 24.04 /
26.04).

**Durum:** Faz 0, teknik denemeler. Henüz kullanılabilir bir uygulama yok.

- Plan: [docs/PLAN.md](docs/PLAN.md)
- Faz 0 denemeleri ve talimatları: [docs/FAZ0.md](docs/FAZ0.md)

## Kurulum

```bash
./scripts/setup_ubuntu.sh
```

Sistem paketlerini kurar (GStreamer PipeWire eklentisi, PyGObject derleme bağımlılıkları,
Qt X11 kütüphaneleri), sonra [uv](https://docs.astral.sh/uv/) ile proje ortamını
hazırlar. Python sistemden bağımsız, uv'nin yönettiği 3.12 sürümüdür.

## Dizin yapısı

| Yol | İçerik |
|---|---|
| `src/gamesentenceminer/` | Uygulama paketi (Faz 1'de dolacak) |
| `tools/spikes/` | Faz 0 deneme betikleri: ortam kontrolü, portal ile ekran yakalama, overlay |
| `tools/dev/` | Geliştirme araçları, ör. GNOME olmadan test için sahte ScreenCast portalı |
| `scripts/` | Kurulum betikleri |
| `docs/` | Plan ve faz notları |
