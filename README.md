# rd200v2
RadonEye RD200 (Version 2 and now Version 1) Integration for Homeasssistant. Throw me a github star if you use this!

[![Stargazers repo roster for @jdeath/rd200v2](https://git-lister.onrender.com/api/stars/jdeath/rd200v2?limit=20)](https://github.com/jdeath/rd200v2/stargazers)

Based on: https://github.com/EtoTen/radonreader/ and the AirThings BLE Homeassistant Integration (https://github.com/home-assistant/core/tree/dev/homeassistant/components/airthings_ble) and https://github.com/vincegio/airthings-ble, and the ESPHome Native Integration (https://esphome.io/components/sensor/radon_eye_ble.html)

Works for RD200 Version 2 units with serial numbers starting with either FR:RU (United States) , FR:RE (Spain), FR:GI, FR:H, FR:GL, FR:I (??? all sold in the US), FR:RD and FR:GJ. Now works for version 1 (FR:R2 serial numbers). V1 integration currently only supports current radon value, 1 day and 1 month readings, peak and uptime. Note the box and the device display do not show the "FR:" portion of the serial number.

If you are pretty sure it is a version 2 device, but has a differnet serial number prefix, edit the manifest.json and line 152 in config_flow.py to include you prefix. If it works, post an issue or a PR and I can add it in.

A python script is posted for people to help find important fields in the V2.

If use ESPHome BT proxy, update to at least ESPHome 2022.12.4 to allow Version 2 radon peak value to work correctly.

If updated to Home Assistant 2024.1.0 or later, please run at least version 4.1 of the integration as previous releases will error. Home Assistant made changes and did not provide any depreciation time buffer. https://github.com/home-assistant/core/issues/107004

If you update to 4.2, you must run Homeassistant 2024.1.0 or later. If you get an error about "close_stale_connections_by_address" you need to update to homeassistant 2024.1.x or revert back to version 4.1 of this integration

If use a Raspberry Pi built-in BT adapter, the Peak and Uptime sensor may not work after the first update and cause itegration to hang. Being investigated. Two options to work around: Use an ESPHome proxy (recommended) or comment out (add a #) to line 257 and 258 of the parser.py, like so:
```
 #device = await self._get_radon_peak(client, device)
 #device = await self._get_radon_uptime(client, device)
```
An issue has been created in homeassistant for the BT performance, but it could just be the Raspberry Pi BT adapter stinks! https://github.com/home-assistant/core/issues/90307

For VMWare: A user solved "regularly loosing-connection" on their Win10/Nuc running Home-Assistant in a VMWare Virtual machine by updating from VMware Pro 15 to VMWare (free) Verions 16. 

### Installation Instructions
- Add this repo into HACS
- Install integration
- Restart Homeassistant
- Wait a few minutes and HA should find it automatically
- If not found automatically, Go to Settings->Device and Services->Add Integration (blue button at bottom right) -> search for RD200
- It should find it and set it up

Note: If used the ESPHome integration in the past, you must remove the RD200 MAC address from the `ble_client:` section. 

### Pusle counter for V2 Devices (Thanks @farlight1)
Now - Actual count pulses (note that this is a real time parameter and it is updated on the device when the ion chamber fires, as we read the device every 10 minutes in HA it may not make sense. Users who want to use this parameter should consider changing DEFAULT_SCAN_INTERVAL in const.py to 1min (60) or almost 2min (120).

Last - Last 10min pulse count until next radon value update.

### Version 2 Data locations:
| Reading | Write Value | Data Location | Data Format | Unit | Added in Integration |
| - | - | - | - | - | - |
| `Current Radon` | `0x50` | `data[2:4]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Day Radon` | `0x50` | `data[4:6]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Month Radon` | `0x50` | `data[6:8]`  | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Radon C pulse now` | `0x50` | `data[8:10]` | little endian ushort | Pulses | Yes |
| `Radon C pulse last` | `0x50` | `data[10:12]` | little endian ushort | Pulses | Yes |
| `Peak Radon` | `0x40` | `data[51:53]` | little endian ushort | Bq/m<sup>3<sup> | Yes |
| `Serial` | `0x40` | `data[8:11] + data[2:8] + data[11:15]` | chars |  | No |  
| `Model` | `0x40` | `data[16:21]` | chars |  | Yes |  
| `Firmware` | `0x40` | `data[22:30]` | chars |  | Yes |  
| `Uptime Minutes Field` | `0x51` | `data[4:8]` | little endian uint | minutes  | Yes |  
| `Uptime seconds Field` | `??` | `??` | little endian ushort | ??  | no: hard coded to 0 | 
