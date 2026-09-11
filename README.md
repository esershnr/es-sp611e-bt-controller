# SP611E BLE RGB LED Controller - CLI & Web Dashboard

SP611E (BanlanX) Bluetooth Low Energy (BLE) RGB LED kontrolcüsü için komut satırı aracı ve yerel web arayüzü.

## Özellikler
- 🔍 **BLE Cihaz Tarama (`scan`)**: Yakındaki cihazları tarar, SP611E kontrolcülerini öne çıkarır.
- 💡 **Güç (`on` / `off`)**, 🔆 **Parlaklık (`brightness`)**: 0-255 veya yüzde.
- 🎨 **Statik Renk (`color`)**: İsim, hex veya RGB bileşenleri; cihazı otomatik olarak statik moda alır.
- 🌈 **Dinamik Efekt (`effect`)** ve ⏩ **Hız (`speed`)**: 1-255 efekt ID, 1-10 hız.
- 🧩 **Toplu Ayar (`set` / kök kısayol)**: `sp611e --color red --brightness 10` gibi birden fazla ayarı tek BLE bağlantısında uygular.
- 🔗 **OpenRGB Senkronu (`openrgb`)**: OpenRGB SDK üzerinden seçilen cihazın rengini şeride canlı aynalar (kalıcı BLE bağlantısı, değişiklik bazlı gönderim).
- 🖥️ **Web Dashboard (`gui`)**: Tarayıcıda renk stüdyosu, parlaklık, efekt ve hız kontrolleri; BLE tarayıcı modalı.
- ⚙️ **Konfigürasyon (`config`)** ve 📜 **Loglar (`logs`)**: `~/.sp611e/` altında varsayılan MAC ve debug logu.
- 📦 **Tek dosya `.exe`**: PyInstaller ile Python gerektirmeyen taşınabilir çalıştırılabilir (bkz. Kurulum A).
- 🛡️ **Tek bağlantı garantisi**: SP611E aynı anda tek BLE bağlantısı kabul eder; tüm erişim kilitle serileştirilir, çoklu komutlar tek bağlantıda gönderilir.
- 🧱 **Donanımdan izole protokol katmanı** (`protocol.py`) ve birim testleri.

---

## Kurulum

Python 3.11 veya daha yeni bir sürüm gereklidir. Üç seçenek var; `sp611e` komutunu her terminalden
doğrudan çalıştırmak istiyorsanız **A** veya **B**'yi seçin.

### A) Tek dosya `sp611e.exe` (PyInstaller) — Python kurulu olmayan makinelerde de çalışır

```powershell
# 1. Sanal ortam + build bağımlılıkları
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[build]"

# 2. Derle -> dist\sp611e.exe (~13 MB, web arayüzü dahil)
pyinstaller sp611e.spec
```

Derlenen dosyayı PATH'teki bir klasöre koyun. Örneğin kullanıcı PATH'ine kalıcı olarak eklemek için:

```powershell
$dest = "$env:LOCALAPPDATA\Programs\sp611e"
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item dist\sp611e.exe $dest
[Environment]::SetEnvironmentVariable(
  "Path",
  [Environment]::GetEnvironmentVariable("Path", "User") + ";$dest",
  "User")
```

Yeni bir terminal açın ve deneyin:

```powershell
sp611e --version
sp611e scan
```

Notlar:
- `sp611e.spec` web klasörünü (`src/sp611e_cli/web`) pakete gömer; `gui` komutu exe'den de çalışır.
- Bleak'in Windows (WinRT) backend'i `hiddenimports` ile pakete eklenir. Derleme sırasında görülen
  `corebluetooth ... No module named 'objc'` uyarısı macOS backend'ine aittir, yok sayılabilir.
- Windows SmartScreen imzasız exe için uyarı verebilir; "Yine de çalıştır" deyin veya kendi sertifikanızla imzalayın.
- Kaynak kodu değiştirdikten sonra `pyinstaller --clean sp611e.spec` ile yeniden derleyin.

### B) `pipx` ile kurulum — Python varsa en pratik yol

```powershell
python -m pip install --user pipx
python -m pipx ensurepath        # ~\.local\bin klasörünü PATH'e ekler (yeni terminal gerekir)
pipx install .                   # proje kökünde
sp611e --version
```

`pipx` izole bir sanal ortam oluşturur ve `sp611e` komutunu PATH'e koyar. Güncellemek için
`pipx reinstall sp611e-cli`, kaldırmak için `pipx uninstall sp611e-cli`.

### C) Geliştirici kurulumu (editable)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

Bu modda `sp611e` yalnızca sanal ortam aktifken (veya `.venv\Scripts\sp611e.exe` tam yoluyla) çalışır;
kaynak değişiklikleri yeniden kurulum gerektirmeden etkili olur.

---

## Kullanım Kılavuzu

### 1. Yakındaki Cihazları Tarama
SP611E kontrolcünüzün MAC adresini öğrenmek için:
```bash
sp611e scan
```

Tüm BLE cihazlarını sinyal gücüyle (RSSI) birlikte listelemek isterseniz:
```bash
sp611e scan --all
```

---

### 2. Cihazı Açma ve Kapatma

#### MAC Adresini Doğrudan Belirterek:
```bash
sp611e --mac AA:BB:CC:DD:EE:FF on
sp611e --mac AA:BB:CC:DD:EE:FF off
```

#### Varsayılan MAC Adresi Tanımlayarak (Tavsiye Edilen):
MAC adresini bir kez yapılandırmaya kaydedin:
```bash
sp611e config --set-mac AA:BB:CC:DD:EE:FF
```

Artık adres belirtmeden doğrudan kontrol edebilirsiniz:
```bash
sp611e on
sp611e off
```

Kayıtlı ayarları görüntülemek için:
```bash
sp611e config
```

---

### 3. Parlaklık Ayarlama (`brightness`)

Parlaklığı 0 - 255 aralığında veya yüzde (%) olarak belirtebilirsiniz:

```bash
# 0-255 aralığında
sp611e brightness 255     # Maksimum parlaklık
sp611e brightness 128     # Orta parlaklık
sp611e brightness 10      # Düşük parlaklık

# Yüzde olarak
sp611e brightness 80%
sp611e brightness 50 -p
```

---

### 4. Statik RGB Renk Ayarlama (`color`)

Renkleri isimle, Hex koduyla (#RRGGBB veya #RGB) ya da ayrı RGB değerleriyle ayarlayabilirsiniz:

```bash
# İsimle (red, green, blue, white, warm-white, yellow, cyan, magenta, orange, purple, pink, turquoise, gold vb.)
sp611e color red
sp611e color warm-white
sp611e color turquoise

# Hex renk koduyla
sp611e color "#FF5733"
sp611e color "#00FF00"
sp611e color "#F00"

# RGB bileşenleriyle
sp611e color 255 128 0
sp611e color 0 255 200

# Renk ile birlikte özel parlaklık belirterek (-b / --brightness)
sp611e color blue -b 100
```

> **Not:** SP611E'de statik renk ayrı bir komut değil, `0xBE` numaralı "Solid Color" modudur.
> Bu yüzden `color` komutu (ve web arayüzündeki Renk Stüdyosu) tek bağlantıda iki çerçeve gönderir:
> önce `A0 63 01 BE` (statik moda geç), ardından `A0 69 04 R G B Parlaklık`. Mod değişimi olmadan
> çalışan bir dinamik efekt yeni rengi yutar ve animasyona devam eder.

---

### 5. Dinamik Efekt Seçimi (`effect`)

Dahili dinamik animasyon efektlerini ID numarası ile seçebilirsiniz:

```bash
# Efekt seç (1-255)
sp611e effect 1
sp611e effect 12

# Efekt seçerken aynı anda hızı da belirle (-s / --speed: 1-10)
sp611e effect 5 -s 8
```

---

### 6. Efekt Oynatma Hızı (`speed`)

Efekt hızını 1 (en yavaş) ile 10 (en hızlı) arasında ayarlayabilirsiniz:

```bash
sp611e speed 1     # En yavaş animasyon akışı
sp611e speed 5     # Orta hız
sp611e speed 10    # En hızlı animasyon akışı
```

---

### 7. Birden Fazla Ayarı Tek Seferde Uygulama (`set`)

Renk, parlaklık, efekt, hız ve güç durumunu tek komutta, **tek BLE bağlantısı** üzerinden gönderebilirsiniz.
Alt komut yazmadan doğrudan kök seviyede de kullanılabilir:

```bash
sp611e --color red --brightness 10          # kısayol (alt komutsuz)
sp611e set --color red --brightness 10      # eşdeğer

sp611e set --on --color "#FF5733" -b 80%    # aç + renk + yüzde parlaklık
sp611e set --rgb 0 0 255 --brightness 50%   # 3 ayrı RGB bileşeni
sp611e set --effect 5 --speed 8             # efekt + hız
sp611e set --color 255,128,0 --off          # rengi kaydet, sonra kapat
```

Seçenekler: `--on`, `--off`, `-c/--color` (isim / `#RRGGBB` / `R,G,B`), `--rgb R G B`, `-b/--brightness`, `-e/--effect`, `-s/--speed`, `-m/--mac`.
Komutlar şu sırayla gönderilir: güç açma → efekt → hız → statik renk (`A0 63 01 BE` + `A0 69 …`) → parlaklık → güç kapatma.
`--color` ile `--effect` aynı anda kullanılamaz (statik renk de bir efekt modudur).

---

### 8. Modern Web Dashboard GUI (`gui`)

Tarayıcınızda açılan şık, karanlık temalı, cam efektli (glassmorphism) ve neon ışıklı interaktif kontrol panelini başlatmak için:

```bash
sp611e gui
```

- Varsayılan tarayıcınızı otomatik olarak açar (`http://127.0.0.1:8080`).
- **Özellikler:**
  - 🌈 **Canlı LED Şerit Simülatörü:** Yapılan renk ve parlaklık ayarlarını ekranda 24 diode üzerinden canlı simüle eder.
  - 🎨 **Renk Çarkı & 16 Hazır Palet:** Tek tıkla renk seçimi, HEX ve RGB kutuları.
  - ☀️ **Dinamik Parlaklık Çubuğu:** Hızlı yüzde butonları (%10, %25, %50, %75, %100).
  - ⚡ **Efekt Kartları & Hız Kontrolü:** Animasyonlu efekt kartları ve 1-10 arası kaydırıcı.
  - 📡 **Entegre BLE Tarayıcı Modalı:** Yakındaki cihazları tek tıkla arayıp hedef seçebilme.
  - 🔘 **Neon Ana Güç Butonu:** Tek tıkla açma/kapama.

Farklı bir port veya host belirlemek isterseniz:
```bash
sp611e gui --port 9000 --no-browser
```

### 9. OpenRGB Senkronizasyonu (`openrgb`)

OpenRGB'de görünen bir cihazın (anakart, RAM, klavye...) rengini SP611E şeridine canlı olarak aynalar.
OpenRGB SDK'sı yeni cihaz kaydına izin vermediği için şerit OpenRGB listesinde görünmez; bunun yerine
seçtiğiniz cihazı **takip eder**. OpenRGB Effects Plugin ile üretilen animasyonlar da bu yolla şeride yansır.

Ön koşul: OpenRGB'de **Settings → SDK Server** etkin olmalı (varsayılan port 6742).

```bash
# OpenRGB'nin gördüğü cihazları ve zone'larını listele
sp611e openrgb --list

# Tek cihaz varsa doğrudan başlat
sp611e openrgb

# Belirli bir cihazı (ad parçası veya indeks) ve isteğe bağlı zone'u takip et
sp611e openrgb --device "ASUS Aura" --zone "RGB Header"
sp611e openrgb -d 0 -z 1

# En parlak LED'i seç, şeride %60 parlaklık uygula, 15 Hz sorgula
sp611e openrgb -d corsair --pick brightest -b 60% --fps 15
```

#### Örnek komutun parça parça açıklaması

```bash
sp611e openrgb -d "ASUS Aura" -z "RGB Header" --pick brightest -b 60% --fps 15
```

| Parça | Anlamı |
|---|---|
| `-d "ASUS Aura"` | Adında "asus aura" geçen OpenRGB cihazını takip et (büyük/küçük harf duyarsız, ad parçası yeterli). |
| `-z "RGB Header"` | O cihazın tamamını değil, yalnızca "RGB Header" zone'unu izle. |
| `--pick brightest` | Zone'daki LED'ler arasından R+G+B toplamı en yüksek olanın rengini al. |
| `-b 60%` | Şeride %60 (= 153/255) parlaklık uygula; renk kalitesini değil, RGB karesinin parlaklık baytını etkiler. |
| `--fps 15` | OpenRGB'yi saniyede 15 kez sorgula → en fazla 15 renk güncellemesi/sn. |

MAC verilmediği için `sp611e config --set-mac` ile kaydedilen varsayılan adres kullanılır.

#### Tüm seçenekler

| Seçenek | Varsayılan | Açıklama |
|---|---|---|
| `--list` | — | OpenRGB'nin gördüğü cihazları `[indeks] ad (LED sayısı)` ve altındaki zone'ları listeler, sonra çıkar. `-d`/`-z` değerlerini buradan seçin. BLE'ye dokunmaz, MAC gerekmez. |
| `--mac`, `-m` | config'teki MAC | Hedef SP611E adresi. Verilmezse `~/.sp611e/config.toml` içindeki varsayılan kullanılır; o da yoksa hata. |
| `--host` | `127.0.0.1` | OpenRGB SDK sunucusunun adresi. OpenRGB başka bir makinede çalışıyorsa onun IP'si. |
| `--port` | `6742` | OpenRGB SDK sunucu portu (OpenRGB > Settings > SDK Server'daki değer). |
| `--device`, `-d` | — | Takip edilecek cihaz. **İndeks** (`-d 0`) veya **ad parçası** (`-d aura`). Adda önce tam eşleşme, sonra kısmi eşleşme aranır; birden fazla cihaz eşleşirse liste ile hata verir. Verilmezse yalnızca OpenRGB'de **tek cihaz** varken çalışır. |
| `--zone`, `-z` | tüm cihaz | Cihazın tek bir zone'unu izle. `-d` ile aynı kurallar: indeks veya ad parçası. Verilmezse cihazın bütün LED'leri kaynak alınır. |
| `--pick` | `avg` | Çok LED'li kaynaktan tek renk türetme yöntemi:<br>• `avg` — her kanalın (R, G, B) ortalaması; gökkuşağı efektlerinde renkler karışabilir.<br>• `first` — kaynaktaki ilk LED'in rengi; dalga/koşan efektlerde net tek renk verir.<br>• `brightest` — R+G+B toplamı en yüksek LED.<br>• `N` (örn. `--pick 3`) — belirli LED indeksi; aralık dışıysa hata. |
| `--fps` | `10` | OpenRGB sorgulama sıklığı (Hz). Bu değer aynı zamanda BLE'ye gidebilecek azami güncelleme hızıdır. SP611E pratikte ~15'ten hızlısını uygulayamaz; efektlerde 10-15 yeterlidir. Statik renkte fps'nin önemi yoktur (aynı renk tekrar gönderilmez). |
| `--brightness`, `-b` | `255` | Şeridin parlaklığı: `0-255` veya yüzde (`60%`). OpenRGB'de parlaklık kavramı olmadığı için burada sabitlenir; `A0 69 04 R G B L` karesindeki `L` baytına yazılır. |
| `--idle-timeout` | `30` | Renk bu kadar saniye değişmezse BLE bağlantısı bırakılır; böylece telefon/CLI cihaza erişebilir. Renk yeniden değişince otomatik bağlanır (bağlantı 1-4 sn sürer). `0` = bağlantıyı asla bırakma (en düşük gecikme). |
| `--no-power-on` | kapalı | Normalde her BLE bağlantısında önce `A0 62 01 01` (aç) gönderilir; bu bayrak ile atlanır. Şeridi OpenRGB'den bağımsız kapalı tutmak isterseniz kullanın. |
| `--help` | — | Seçenek listesi. |

Köprüyü durdurmak için **Ctrl+C**; kapanışta gönderilen kare sayısı yazdırılır ve BLE bağlantısı kapatılır.

Çalışma mantığı:
- BLE bağlantısı **kalıcı** tutulur (her karede bağlan/kopar yapılmaz; bağlantı 1-4 sn sürer).
- Sadece **değişen** renk gönderilir; OpenRGB aynı rengi tekrarlasa bile BLE'ye tekrar yazılmaz.
- Her bağlantıda bir kez statik mod (`A0 63 01 BE`) seçilir, sonra yalnızca renk kareleri (`A0 69 04 ...`) akar.
- OpenRGB kapalıysa/kapanırsa köprü 3 sn aralıkla yeniden bağlanmayı dener; BLE hatasında 2 sn sonra tekrar dener.

> [!NOTE]
> Köprü çalışırken SP611E'nin tek bağlantısı köprüde olduğundan `sp611e color ...` veya web arayüzü
> **başka bir süreçten** cihaza erişemez. `--idle-timeout` süresi dolunca bağlantı serbest bırakılır.

---

## Önemli Notlar & Sorun Giderme

> [!IMPORTANT]
> **Tek Bağlantı Kısıtı (Single Connection Limit):**  
> SP611E çipi aynı anda **yalnızca tek bir Bluetooth bağlantısına** izin verir. Eğer akıllı telefonunuzda BanlanX uygulaması açıksa veya arka planda cihaza bağlıysa, bilgisayardan gönderilen komutlar bağlantı hatası verecektir.  
> **Çözüm:** Telefonunuzda BanlanX uygulamasını tamamen kapatın ve gerekirse telefon Bluetooth'unu geçici olarak kapatıp tekrar deneyin.

---

## Testler

Protokol ve CLI testlerini çalıştırmak için:
```bash
pytest -v
```

---

## Teknik Referans (Reverse Engineering)

- **Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
- **Write Characteristic UUID:** `0000ffe1-0000-1000-8000-00805f9b34fb`
- **Protokol Çerçevesi:** `0xA0 + CMD + LEN + PAYLOAD`
  - Aç (`ON`): `A0 62 01 01`
  - Kapat (`OFF`): `A0 62 01 00`
