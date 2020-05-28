# Copyright (C) 2009-2010, 2020 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Matthew Ruffell <matthew.ruffell@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Grub Dpkg
---------
**Summary:** configure grub debconf installation device

Configure which device is used as the target for grub installation. This module
should work correctly by default without any user configuration. It can be
enabled/disabled using the ``enabled`` config key in the ``grub_dpkg`` config
dict. The global config key ``grub-dpkg`` is an alias for ``grub_dpkg``. If no
installation device is specified this module will execute grub-probe to
determine which disk the /boot directory is associated with.

The value which is placed into the debconf database is in the format which the
grub postinstall script expects. Normally, this is a /dev/disk/by-id/ value,
but we do fallback to the plain disk name if a by-id name is not present.

If this module is executed inside a container, then the debconf database is
seeded with empty values, and install_devices_empty is set to true.

**Internal name:** ``cc_grub_dpkg``

**Module frequency:** per instance

**Supported distros:** ubuntu, debian

**Config keys**::

    grub_dpkg:
        enabled: <true/false>
        grub-pc/install_devices: <devices>
        grub-pc/install_devices_empty: <devices>
    grub-dpkg: (alias for grub_dpkg)
"""

import os

from cloudinit import util
from cloudinit.util import ProcessExecutionError

distros = ['ubuntu', 'debian']


def fetch_idevs(log):
    """
    Fetches the /dev/disk/by-id device grub is installed to.
    Falls back to plain disk name if no by-id entry is present.
    """
    disk = ""
    devices = []

    try:
        # get the root disk where the /boot directory resides.
        disk = util.subp(['grub-probe', '-t', 'disk', '/boot'],
                         capture=True)[0].strip()
    except ProcessExecutionError as e:
        # grub-common may not be installed, especially on containers
        # FileNotFoundError is a nested exception of ProcessExecutionError
        if isinstance(e.reason, FileNotFoundError):
            log.debug("grub-common is not installed, e.g. inside a container")
        # disks from the container host are present in /proc and /sys
        # which is where grub-probe determines where /boot is.
        # it then checks for existence in /dev, which fails as host disks
        # are not exposed to the container.
        elif "failed to get canonical path" in e.stderr:
            log.debug("Device mapping between /proc/self/mountinfo does not "
                      "match /dev, e.g. inside a container")
        else:
            # something bad has happened, continue to log the error
            raise
    except Exception:
        util.logexc(log, "grub-probe failed to execute for grub-dpkg")

    try:
        # check if disk exists and use udevadm to fetch symlinks
        if os.path.exists(disk):
            devices = util.subp(['udevadm', 'info', '-r',
                                '--query=symlink', disk],
                                capture=True)[0].strip().split()
    except Exception:
        util.logexc(log, "udevadm failed to gather devices for grub-dpkg")

    # filter symlinks for /dev/disk/by-id entries
    devices = [dev for dev in devices if 'disk/by-id' in dev]
    # select first device if there is one, else fall back to plain name
    idevs = sorted(devices)[0] if devices else disk

    return idevs


def handle(name, cfg, _cloud, log, _args):

    mycfg = cfg.get("grub_dpkg", cfg.get("grub-dpkg", {}))
    if not mycfg:
        mycfg = {}

    enabled = mycfg.get('enabled', True)
    if util.is_false(enabled):
        log.debug("%s disabled by config grub_dpkg/enabled=%s", name, enabled)
        return

    idevs = util.get_cfg_option_str(mycfg, "grub-pc/install_devices", None)
    idevs_empty = util.get_cfg_option_str(
        mycfg, "grub-pc/install_devices_empty", None)

    if idevs is None:
        idevs = fetch_idevs(log)
    if idevs_empty is None:
        idevs_empty = "false" if idevs else "true"

    # now idevs and idevs_empty are set to determined values
    # or, those set by user

    dconf_sel = (("grub-pc grub-pc/install_devices string %s\n"
                 "grub-pc grub-pc/install_devices_empty boolean %s\n") %
                 (idevs, idevs_empty))

    log.debug("Setting grub debconf-set-selections with '%s','%s'" %
              (idevs, idevs_empty))

    try:
        util.subp(['debconf-set-selections'], dconf_sel)
    except Exception:
        util.logexc(log, "Failed to run debconf-set-selections for grub-dpkg")

# vi: ts=4 expandtab
