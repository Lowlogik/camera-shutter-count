# Camera Shutter Count

Windows app that reads the shutter actuation count from a camera over USB.

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?logo=github)](https://github.com/sponsors/patricktheroux-ops)

Tested on a **Rebel T7** (firmware 1.1.0), Windows 11. Want another camera added? [Open an issue](https://github.com/patricktheroux-ops/camera-shutter-count/issues).

This talks to the camera through Windows Portable Devices (the same WPD/MTP stack Explorer uses). No WinUSB driver swap. Most JPEG/RAW files do not store a true shutter count.

## Download

[**Camera Shutter Count.exe**](https://github.com/patricktheroux-ops/camera-shutter-count/releases/latest) — Windows 10/11.

Windows may warn that the app is unsigned. That’s expected until it’s signed. Close other camera software / Photos, plug the camera in with a data cable, turn it **on**, then click **Read shutter count**.

## Tested

- Rebel T7 (firmware 1.1.0), Windows 11

If you have another body and want it listed, [open an issue](https://github.com/patricktheroux-ops/camera-shutter-count/issues) with the model.

Some cameras do not expose the count over USB. `IMG_1234` file numbers are **not** a shutter count.

## Run from source

```powershell
python -m pip install -r requirements.txt
python app.py
```

CLI:

```powershell
python shutter_count.py
```

Close other camera software, Photos, and Camera first. Use a data USB cable and turn the camera **on**.

## Build the .exe

```powershell
.\build.ps1
```

Writes `dist\Camera Shutter Count.exe`.

## Sponsor

If this saved you a guess on a used body: [GitHub Sponsors](https://github.com/sponsors/patricktheroux-ops).

## License

MIT
