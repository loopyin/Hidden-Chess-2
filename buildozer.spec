[app]
icon.filename = %(source.dir)s/icon.png
android.presplash_lottie = assets/lottie/hidden_chess_presplash_7s_lottie.json
android.presplash_color = #000000

# (str) Title of your application
title = Hidden Chess

# (str) Package name
package.name = hiddenchess

# (str) Package domain (needed for android/ios packaging)
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,ttf,json,wav,ogg
source.include_patterns = assets/themes/**,assets/sounds/**,assets/*.ttf,assets/*.png,assets/*.json,assets/lottie/*.json

# (str) Application versioning
version = 1.5.403

# (list) Application requirements
requirements = python3==3.10.14,hostpython3==3.10.14,pygame,certifi,openssl

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 1

# (list) Permissions
android.permissions = INTERNET

# (bool) If True, then automatically accept SDK license
android.accept_sdk_license = True

# (list) The Android archs to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a, armeabi-v7a

# (str) python-for-android branch to use
p4a.branch = develop

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
