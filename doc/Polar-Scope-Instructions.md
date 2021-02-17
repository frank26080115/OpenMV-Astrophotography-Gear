**work in progress**

## Shopping List

Required:

 * [OpenMV H7 Plus](https://openmv.io/collections/products/products/openmv-cam-h7-plus)
 * [Super-telephoto lens for OpenMV](https://openmv.io/collections/lenses/products/super-telephoto-lens)
   * this is just a 25mm focal length lens for M12 mounts
   * if you do not use the exact same lens that I used, you may need to re-calibrate all of the plate solving databases
 * [WiFi shield for OpenMV](https://openmv.io/collections/shields/products/wifi-shield-1)
 * 3x M3 nylon screw, 8mm long
   * use three more M3 screws if you are using a QHY adapter
 * USB power bank and USB micro cable

Optional:

 * rubber O-ring, ID 11 mm, OD 13 mm, hardness 70A
   * wrapped around the lens, used to make focus adjustments easier
 * you can get a tiny screw to lock in the focus, but I don't know what size

There are other screws that might be required depending on how you plan on mounting the camera

## 3D Print

There's a 3D printed mount you can print out to hold the camera. The 3D model is available in the [mech folder of my GitHub repo](../mech/README.md). It requires additional drilling and thread-tapping. Use a M3 thread tap on all the holes. The 1/4"-20 threaded insert being used is [McMaster-Carr 90594A024](https://www.mcmaster.com/90594A024/).

If you do decide to use this 3D printed mount, you should enlarge the holes on the OpenMV with a 1/8" drill bit. Otherwise, the M3 screws will not fit.

## First Steps

When you buy everything, remove the default lens from the OpenMV, place the O-ring on the threads of the telephoto lens, and screw in the telephoto lens into the mount.

(you may want to clean the sensor, but according to the creators of OpenMV, newer cameras are already cleaned at the factory)

Attach the WiFi shield to the OpenMV. This may require soldering.

Download and install [OpenMV IDE](https://openmv.io/pages/download)

Plug in the OpenMV to your computer, use OpenMV IDE to update the firmware of the OpenMV. You **MUST** use my firmware from [this GitHub repo file](https://github.com/frank26080115/OpemMV-Astrophotography-Gear/blob/master/openmv_fw/firmware.bin)

Download everything from the [file system directory](https://github.com/frank26080115/OpemMV-Astrophotography-Gear/tree/master/openmv_filesys), and copy it into the OpenMV's flash memory. (it should have appeared as an USB drive)

## Power

Simply power the device by a USB power bank and a USB micro cable

## WiFi Settings

By default, the WiFi is not configured. It will run as a soft-access-point with SSID similar to `OpenMV-XXXX`. Connect to it with a smartphone, the password will be `1234567890`. When you are connected, you can access the web interface with the address `http://192.168.1.1/`.

Otherwise, you can also create a file on the flash memory drive named `wifi_settings.json`, with the contents similar to:

    {
      "ssid": "your-router-ssid",
      "mode": "home",
      "password": "1234567890",
      "security": "wpa"
    }

Which will allow you to connect to a router. You will need to check the router to see which IP address is assigned to the OpenMV. For example, if the router assigned it the IP of `192.168.1.123` then you can access the web interface with the URL `http://192.168.1.123/`

If you want to run in soft-access-point mode (which requires no router) while customizing the SSID and password, the contents will look like:

    {
      "ssid": "new-name",
      "mode": "soft-ap",
      "password": "new-password",
      "security": "wep"
    }

(only WEP is supported for soft-AP mode)

## Adjust Focus

At night, you have pointed the camera at the stars, and you are looking at the web interface. The first thing you need to do is make sure the lens is focused correctly.

Use the web interface to turn on `Real Image` mode, then rotate the lens until the stars are in focus. You may also change the zoom level and the camera exposure settings.

## Adjust Exposure

The camera's exposure settings may be changed to get the best image. The best image is one in which the code can detect the most amount of stars without detecting any noise as if they were stars. If you are pointing at Polaris already, seeing 15 to 20 stars should be an excellent result.

There are three settings: gain, shutter, and threshold.

Gain is the electronic amplifier of the camera sensor. The higher it is, the brighter the overall image becomes. This will help dark stars be seen but it will also amplify noise. Changing it will not affect the frame-rate of the camera.

The shutter speed adjustment will affect how much light is gathered by the camera sensor. The longer the shutter time is, the more light is gathered, and stars will be brighter without collecting noise. But a longer shutter time (i.e. slower shutter speed) will slow down the frame-rate.

The threshold adjustment tells the code "how bright a star is". The higher the setting, the less stars will be detected. You want to raise it high enough that noise is not confused for stars. If you leave it at zero, then the code will make a best-guess of the threshold based on the overall image darkness.

## Center Calibration

Calibration must be done every time you attach the camera to a tracking mount. If you calibrate it and then leave it mounted, you shouldn't need to re-calibrate. (but it might still be a nice idea)

You must be pointed at Polaris. Polaris and NCP must be positively identified (you will see a red marker on the NCP and a green dot over Polaris).

Register that image with the button `Register Image Data`.

Rotate the R.A. axis of your tracking mount (ideally with the electric motor, not using your hand) about 90°, Polaris and NCP must still be in-view. Do not move the tripod.

Click the `Calibrate` button. The yellow crosshair on the image should have moved to the new calibrated location.

## Polar Alignment

If Polaris and the NCP are detected properly, you will see a red marker on the NCP and a green dot over Polaris. There should also be an artificial horizon in the corner of the image indicating which way is up and down.

Use the latitude and azimuth adjustment knobs on your tracking mount to move the yellow crosshair into the center of the red marker. You may use the different zoom levels for extra precision.

## Atmospheric Refraction

If you want to enable atmospheric refraction compensation, go into the "Time and Location" tab and enable it via the checkbox. Make sure you've inputted the correct geographic location. The settings can be saved for next time.

## Hot Pixels

If you think you have good camera exposure settings but you see stars that don't move even if the camera is being moved, then you are seeing hot-pixels. Go into the "Hot Pixels" tab, cover up the lens completely, raise the camera gain a little bit higher, and click "Capture Hot Pixels". After that, the code will remove the hot pixels from view.

## Advanced Usage

You may use OpenMV IDE to do whatever you want. The whole project is open source. You can run the default camera viewing demo code and use your computer to check the camera if you wish.

There's a `polarscope_settings.json` file. You can make manual edits to it if you wish but you do need to reset OpenMV, and then refresh the web interface, to make the changes take effect.

If you ever mess up, you can always just delete everything and start all over.

----------

[click here to go back to the polar scope page](https://frank26080115.github.io/OpenMV-Astrophotography-Gear/doc/Polar-Scope)
