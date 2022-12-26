import asyncio
import binascii
import struct 
from bleak import BleakClient, BleakGATTCharacteristic

SCALE_MAC = "24:4C:XX:XX:XX:XX"
RADON_CHARACTERISTIC_UUID_READ = "00001525-0000-1000-8000-00805f9b34fb"
RADON_CHARACTERISTIC_UUID_WRITE = "00001524-0000-1000-8000-00805f9b34fb"
WRITE_VALUE = b"\x50"

def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    print(f"Received message on {characteristic.uuid}: {binascii.hexlify(data)}")
    RadonValueBQ = struct.unpack('<H',data[2:4])[0]
    RadonValuePCi = ( RadonValueBQ / 37 )
    print("Radon Value: " + str(round(RadonValuePCi,2)) + " pC/l")

async def main():
    print("Connecting...")
    async with BleakClient(SCALE_MAC) as client:
        print(f"Connected: {client.is_connected}")

        print("Services discovered:")
        for service in client.services:
            print(service)
        
        write_value = b"\x50"
        await client.write_gatt_char(RADON_CHARACTERISTIC_UUID_WRITE, write_value)
        
        print("calling start_notify")
        await client.start_notify(RADON_CHARACTERISTIC_UUID_READ, notification_handler)

        await asyncio.sleep(5.0)
        await client.stop_notify(RADON_CHARACTERISTIC_UUID_READ)  

asyncio.run(main())
