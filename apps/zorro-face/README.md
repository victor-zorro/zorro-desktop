# zorro-face

Face unlock with the laptop's infrared camera (the Windows Hello kind), for the zorro-dm
lock screen and, if you want, the login. The password always works too.

- **Camera:** the video device that only gives greyscale frames (found by its stable
  `/dev/v4l/by-path` name). Its IR light is switched on with a vendor control
  (UVC extension unit 14, selector 6 → `1 3 3 …` on the T14 Gen 1's Chicony camera) and
  then flashes on every other frame.
- **Recognition:** OpenCV's YuNet (finds the face) and SFace (128 numbers per face), both
  from the OpenCV model zoo, and the FacemarkLBF model for the wireframe, downloaded and
  checked by sha256 in `install.sh`.
- **Not fooled by a phone:** a frame only counts when the face is clearly brighter in the
  lit frame than in the dark frame next to it. A screen shows black in infrared.
- **Learning window** (`faceview.py learn`, from the Zorro app): your live infrared
  picture as a mirror; every view that is learned adds lines to a wireframe of your face
  (68 points from OpenCV's FacemarkLBF, triangulated, growing from the nose outwards), with
  hints to turn your head. Below it a **strength bar**: how alike your views are (so how far
  above a stranger, who scores about 0.25), how many head angles (straight, left, right, up,
  down) and how many views. At the end the views go to root with `pkexec zorro-face save`.
- **Delete all my face data** (`faceview.py forget`): your wireframe comes apart line by
  line, then the views root keeps and the wireframe file are gone.
- **The frames:** ffmpeg passes every camera frame on unchanged, and only neighbours that
  differ in brightness count as a lit/dark pair (a real face: ~50-65 difference; at least
  20 needed).
- **Faces:** `/var/lib/zorro-face/USER.npy`, root only. Learning again (glasses, other
  light) adds to what is there.
- **Settings:** `/etc/zorro-face.json`: `lock` and `login` (both on: where the face icon
  shows; after a face login the keyring stays closed, a face can't open it), `threshold`
  (0.5), `need` (2 frames in a row).

```
sudo apps/zorro-face/install.sh      # models, /usr/local/bin/zorro-face, polkit rule
zorro-face status zorro
```
Learn your face in the Zorro app → Look → Face unlock (asks your password).
The login and lock screen show a small face icon under the password field (only when a
face is learned); pressing it runs `zorro-face verify USER` in zorro-dm. Nothing scans by
itself, and the password keeps working while it looks.

After a boot or a hibernate the password is needed once first, like on a phone: until
then the face icon stays away. A normal sleep (lid closed, suspend) keeps face unlock.
zorro-dm notes a right password in `/run/zorro-dm/password-ok/USER` (gone at reboot);
its system-sleep hook (`apps/zorro-dm/zorro-dm.sleep`) removes it before a hibernate.
