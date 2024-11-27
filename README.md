# dahua-twilight

by [Scott Smitelli](mailto:scott@smitelli.com)

https://www.scottsmitelli.com/

Switch Amcrest/Dahua IP cameras from day to night profiles based on local sunrise and sunset times.

## Note

As far as I can tell, Amcrest cameras are simply Dahua cameras with the branding changed. Tools and techniques that work with Dahua hardware will work with Amcrest, and vice-versa. To avoid needless repetition, I will only say "Dahua" going forward, but just remember that the information tends to apply equally to "Amcrest" as well.

## Background

Dahua cameras have multiple **color modes** available: Full color for daylight or artificial lighting, and black-and-white (B&W) for low light situations. The B&W mode responds highly to infrared light, and these cameras tend to have an onboard IR LED for use with the B&W mode. Color/IR settings (as well as all the other color/exposure/noise reduction options) belong to a configuration element called a **profile**. Dahua uses names like **Day**, **Night**, and **General** but _the profile names do not necessarily correspond to the color mode._ You would do well to think of these as **Profile #1**, **Profile #2**, and so on instead.

To be explicit, it is possible to configure the Day profile to be black-and-white with the IR LED enabled, and the Night profile for full color. The camera will let you do this, although for your own sanity it's best to use the profiles as they were intended. This example is merely to help you build your mental model and to try to explain why the (baffling) UI works the way it does.

Profiles have **scheduling options**. The most straightforward options are **General**, **Full-Time Day**, and **Full-Time Night**. Each of these sets the camera to use the corresponding named profile at all times.

Another option is **Schedule**. This permits the user to manually set a sunrise and sunset time using a pair of sliders. The camera will switch to the Day profile whenever the time is between sunrise and sunset, and the Night profile from sunset to sunrise the following day. For best results, avoid using any "auto" options in these profiles -- especially for settings that pertain to color/B&W or IR light. The General profile is not used in Schedule mode.

The final option is **Day/Night**. This mode is a bit of a box of rats. The idea is that it will switch the camera between the Day and Night profiles based on the amount of light entering the camera. However, this commandeers the color settings under the camera's Day/Night sub-options and prevents things like e.g. the sensitivity from being changed. _If you pick this mode, it will change setting within your profiles that you might not expect it to._

The Day/Night selection logic can sometimes be tricked by (e.g.) the glare from up nearby headlights. In fact, after I pressure-washed my driveway and removed a surface layer of dark crud, one of my cameras started refusing to automatically switch to night mode due to the scene being insufficiently dark.

## dahua-twilight's Goals

dahua-twilight uses the Schedule mode, which requires the administrator of the cameras to configure the Day and Night profiles as needed _without_ choosing any of the automatic color or IR options. Every day, dahua-twilight evaluates the local sunrise and sunset times and updates the time sliders on the Schedule page. In the rare event that the user is located at a place and time where there is constant daylight or constant night (polar regions) the Full-Time Day or Night profiles are selected instead.

dahua-twilight does not directly switch profiles, only schedules. This means that if dahua-twilight disconnects, crashes or otherwise fails to perform its regular tasks, the camera will still continue to follow whatever schedule was last configured. The day/night transitions will continue to occur, however the _times_ of these transitions will gradually grow more incorrect until dahua-twilight is brought back to working order.

Additionally, dahua-twilight is designed to run on the inhospitable camera LAN. In my deployment, the camera LAN has the following properties:

- One network video recorder (NVR)
- At least one IP camera
- NVR provides IP addresses via DHCP and responds to NTP messages
- No working route to the internet
- No DNS servers
- Typically no PCs or other client computers on this network

This has a few unusual implications. Firstly, the software needs to be completely self-contained without any runtime dependencies that require an internet connection. Because there are usually no other computers on this network, the software needs to be able to run headless, recover from all conceivable kinds of transient failure, and must generally not be an unreliable thorn in my side.

Each of the cameras is password protected, so the software needs a list of camera credentials along with a mapping of which credential belongs to which camera.

While the NVR provides DHCP, it does not advertise its NTP service to clients. The NVR IP address would need to be statically configured into the OS's NTP client. But read on.

Dahua cameras and NVRs broadcast their presence using UDP packets on port 5050. The NVR announces itself several times each minute, and each camera advertises itself roughly once every two minutes. By listening to this gossip and decoding the payload, it's possible to avoid static configuration for most aspects of the network. Whenever possible, dahua-twilight tries to dynamically configure itself.

## Design

dahua-twilight was designed to run on an aging Raspberry Pi that no longer seemed adequate for interactive use.

dahua-twilight is made from several interconnected subsystems. This is a brief description of what each one does.

**Discovery.** This system listens for packets on UDP port 5050 on all available interfaces. When it receives a packet, it determines whether the packet looks like it came from the NVR or if it came from a camera. In the case of a camera packet, there are a number of identifying fields (hostname, MAC address, serial number, firmware version, etc.) encoded in the packet that are extracted. The list of recently-seen NVRs and cameras is maintained by this system.

**Clock.** dahua-twilight assumes the system clock is wrong, and does not rely on any absolute OS time services. While it is important that the system have some kind of good-quality monotonically increasing seconds counter, it does not need to accurately reflect the time or date. Instead, the clock module performs an SNTP query against the NVR (once one has been found via discovery) and that is used as the true time and date. This alleviates the need to worry about configuring the OS clock.

**Astro.** The astro module is responsible for calculating the sunrise and sunset times for a point on the earth on a given date. It can calculate this down to the second.

**Dahua Client.** This is a set of helper functions that encapsulate the HTTP chicanery to read and write configuration values from/to a Dahua camera. This is by no means a full-featured library; only the necessary functionality has been implemented.

**Config and Log.** These provide a centralized set of functions to read settings from the config file and write timestamped output to the log.

## Config

TODO

## Contributing

In all honesty, I would prefer that you didn't. This project exists principally for use with my specific camera system based on my own very specific and bullheaded requirements. I'm not all that interested in adding functionality that I'm not going to use, and I especially don't want to incorporate features that I can't test. I do not own an extensive collection of camera hardware, and what I do own is part of a production system that I can't afford to dork around with.

Having said that, I encourage anybody to poke through the code, fork it, extend it, whatever. All I ask is that you credit this project appropriately.

## License

MIT, except for a few bits I adapted from the [Astral](https://github.com/sffjunkie/astral) project.
