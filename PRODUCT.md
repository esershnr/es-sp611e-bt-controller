# Product

## Platform

web

## Users

Masaüstü/PC başında çalışan, telefonundaki BanlanX uygulamasına ihtiyaç duymadan SP611E RGB LED şeritlerini doğrudan terminalden veya modern bir web gösterge panelinden kontrol etmek isteyen geliştiriciler, oyuncular ve masa başı kullanıcıları.

## Product Purpose

SP611E (BanlanX) Bluetooth Low Energy (BLE) RGB LED kontrolcüsü için resmi bir PC yazılımı bulunmamaktadır. Bu ürün, donanımı doğrudan bilgisayar üzerinden terminal komutları (`sp611e`) ve yerel modern bir Web Dashboard arayüzü (`sp611e gui`) ile yönetilebilir kılar. Başarı, sıfır gecikmeli, kesintisiz ve telefona bağımlı olmadan ortam aydınlatmasını kontrol edebilmektir.

## Positioning

Piyasadaki kapalı kaynaklı ve yalnızca mobil cihazlarla sınırlı BanlanX ekosistemini masaüstüne taşıyan, BLE reverse-engineering tabanlı, tamamen açık kaynak, hafif ve hem CLI hem de fütüristik Web GUI sunan bağımsız kontrol aracı.

## Operating Context

- Windows işletim sistemi üzerinde Bluetooth LE adaptörü aktif masaüstü/dizüstü bilgisayarlar.
- Terminal / PowerShell ortamından tek satırlık hızlı komutlar (`sp611e on`, `sp611e color blue`, `sp611e brightness 50%`).
- Tarayıcı üzerinden görsel ve ambiyans odaklı etkileşimli kontrol (`http://127.0.0.1:8080`).
- Arka planda çalışan Python `aiohttp` yerel sunucusu ve `bleak` asenkron BLE istemcisi.

## Capabilities and Constraints

- **Onaylanmış Yetenekler:**
  - BLE Cihaz Tarama (`scan`) ve SP611E kontrolcülerini otomatik filtreleme.
  - Açma / Kapama (`on` / `off`).
  - Statik RGB Renk Ayarı (`color`: İsimler, Hex kodları, RGB üçlüleri).
  - Parlaklık Ayarı (`brightness`: 0-255 seviyesi veya yüzde %).
  - Dinamik Işık Efektleri (`effect`: 1-255 arası modlar).
  - Efekt Hız Kontrolü (`speed`: 1-10 aralığı).
  - Toplu ayar (`set` / kök kısayol): birden fazla ayarı tek BLE bağlantısında uygulama.
  - Tek dosya `sp611e.exe` derlemesi (PyInstaller).
  - Kalıcı Varsayılan MAC Adresi Saklama (`~/.sp611e/config.toml`).
  - Dönen (Rotating) Hata Ayıklama Logları (`~/.sp611e/sp611e.log`).
  - İnteraktif Web Dashboard GUI (`sp611e gui`).
  - OpenRGB SDK köprüsü (`sp611e openrgb`): OpenRGB cihazının rengini şeride canlı aynalama; kayıtlı varsayılanlar, arka plan süreci ve oturum açılışında otomatik başlatma.
- **Teknik Kısıtlar:**
  - SP611E çipi aynı anda **yalnızca tek bir Bluetooth bağlantısını** destekler. Akıllı telefonda BanlanX uygulaması açıkken PC'den bağlantı kurulamaz.
  - BLE Service UUID: `0000ffe0-0000-1000-8000-00805f9b34fb`.
  - Write Characteristic UUID: `0000ffe1-0000-1000-8000-00805f9b34fb` (Write-without-response).
  - Komut çerçevesi: `0xA0 + CMD + LEN + PAYLOAD`.

## Brand Commitments

- **İsim:** SP611E Neo (Web Dashboard) / `sp611e` (CLI)
- **Görsel Kimlik:** Cyberpunk / Neo-Glassmorphism karanlık tema, dinamik RGB ambiyans ışıması, fütüristik 'Outfit' ve 'Inter' tipografisi.

## Evidence on Hand

- Gerçek SP611E donanımı üzerinde doğrulanmış komut seti (güç, renk, parlaklık, efekt, hız).
- Reverse-engineered protokol referansı (monty68/uniled `banlanx2.py`).
- 49 adet bağımsız çalışan birim test (`pytest -q`).
- Çalışır durumdaki Python paketi (`pyproject.toml`, `src/sp611e_cli/`).

## Product Principles

1. **Sıfır Sürtünme (Zero Friction):** Adresi bir kez kaydet, sonrasında parametresiz doğrudan çalıştır (`sp611e on`, `sp611e color red`).
2. **Kapsamlı ve Anlaşılır Hata Geri Bildirimi:** Tek bağlantı kısıtı veya Bluetooth kapalı olma durumlarında kullanıcıya tam olarak ne yapması gerektiğini açıkça söyle.
3. **Donanımdan İzole Protokol:** Byte üretim mantığı (`protocol.py`) I/O ve donanım bağımlılıklarından tamamen bağımsız kalsın ve birim testlerle korunabilsin.
4. **Zengin Görsel Deneyim:** Web arayüzü sıradan bir form değil; canlı LED simülatörü, dinamik ambiyans ve neon estetiğiyle kullanıcıyı etkileyen üst düzey bir kontrol paneli olsun.
