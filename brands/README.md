# Brand images

Original artwork for this integration: an infrared beam being emitted from the letter "D". It deliberately contains no Daikin logo, wordmark or mascot.
Daikin is a trademark of Daikin Industries, Ltd., and this project is not affiliated with them.

| File          | Size    | Purpose          |
| ------------- | ------- | ---------------- |
| `icon.png`    | 256×256 | integration icon |
| `icon@2x.png` | 512×512 | hi-dpi icon      |

> [!NOTE]
> Home Assistant does not read these from this repository.
> The frontend loads brand images from [home-assistant/brands](https://github.com/home-assistant/brands).
> To make the icon show up in HACS and the integrations page, we need to copy both files to `custom_integrations/daikin_ir/` in a fork of that repo and open a pull request. No `logo.png` is provided; brands falls back to the icon when a logo is absent.
