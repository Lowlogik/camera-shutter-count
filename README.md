# Camera Shutter Count

Windows app that reads the shutter actuation count from a **Canon EOS** camera over USB.

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?logo=github)](https://github.com/sponsors/patricktheroux-ops)

Canon does not put shutter count in most JPEG/CR2 files. This talks to the camera through Windows Portable Devices (the same WPD/MTP stack Explorer uses). No WinUSB driver swap.

## Download

[**Canon Shutter Count.exe**](https://github.com/patricktheroux-ops/canon-shutter-count/releases/latest) — Windows 10/11.

Windows may warn that the app is unsigned. That’s expected until it’s signed. Close EOS Utility / Photos, plug the camera in with a data cable, turn it **on**, then click **Read shutter count**.

## Tested

- Canon EOS Rebel T7 / EOS 2000D / Kiss X90 (firmware 1.1.0), Windows 11

Other DIGIC 4 / 5 / 5+ DSLRs use the same USB property (`0xD1AC`) and **should** work. They are not tested here yet.

## Likely USB readout

Rebel T3–T7, 2000D / 1500D, 60D / 70D, 7D / 7D Mark II, 5D Mark II / III, and similar-era EOS DSLRs.

## Usually no USB count

Canon dropped that readout on DIGIC 6 and newer: 80D, 5D Mark IV, Rebel T6i / T6s, most EOS R / RP / R7 / R10, EOS M. A Canon service centre can still read those bodies. `IMG_1234` file numbers are **not** a shutter count.

## Run from source

```powershell
python -m pip install -r requirements.txt
python app.py
```

CLI:

```powershell
python shutter_count.py
```

Close EOS Utility, Photos, and Camera first. Use a data USB cable and turn the camera **on**.

## Build the .exe

```powershell
.\build.ps1
```

Writes `dist\Canon Shutter Count.exe`.

## Sponsor

If this saved you a guess on a used body: [GitHub Sponsors](https://github.com/sponsors/patricktheroux-ops).

## License

MIT
