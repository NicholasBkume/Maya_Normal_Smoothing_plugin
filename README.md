# Abnormal
Blender Abnormal add-on for vertex normal editing

This add-on is funded by the BNPR community with the BEER dev fund.

**Please Donate to Keep the Add-on Updated:** https://bnpr.gumroad.com/l/abnormal

## How to use Abnormal
Documentation, tips and tricks: https://bnpr.gitbook.io/abnormal-wiki/

## First Installation:
1. Download the add-on: https://github.com/bnpr/Abnormal/releases
2. Install Abnormal: Preference > Add-on tab > Install
3. Activate the add-on

## Reinstallation:
1. Cleanly remove older Abnormal add-on: preference > Add-on tab, find Abnormal, click remove.
2. Download the add-on: https://github.com/bnpr/Abnormal/releases
3. Install Abnormal: Preference > Add-on tab > Install
4. Restart Blender
5. Activate the add-on (reactivate before Blender restart may cause error message to pop up)

## Reporting a bug:
1. Download the latest add-on version. Please see **Reinstallation** guide above.
2. Recreate the bug in the new add-on
3. Report the bug/issue via this link: https://github.com/bnpr/Abnormal/issues
4. Please describe the bug with the final console print and propose a fix (if possible).


## Maya version

The Maya 2024+ / Python 3 port is in [`maya/`](maya/README.md).
[Download the 0.9.0 full-feature candidate](maya/releases/AbnormalMaya-0.9.0.zip?raw=true).
It includes corner/region picking, topology selection, live target and rotation
manipulators, unified history, saved preferences, scoped shortcuts and VP2 drawing.
The previous 0.2.1 version passed its Maya 2025 suite; new 0.9.0 host validation
is pending. See the [port matrix](maya/PORT_STATUS.md) before making compatibility
or production-readiness claims.
