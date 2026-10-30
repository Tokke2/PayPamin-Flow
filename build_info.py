"""Identity and file fingerprint of the release that supplied this app build.

Release packaging stamps the numeric GitHub release ID, full source commit and
a fingerprint of every shipped file except this self-referential metadata file.
All values are intentionally empty in a source checkout and are separate from
the user-facing app version.
"""

APP_RELEASE_ID = ""
APP_RELEASE_COMMIT = ""
APP_PACKAGE_FINGERPRINT = ""
