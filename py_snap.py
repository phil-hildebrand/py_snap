#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Creat LVM based snapshots for Backups
Expects Space on existing volume group for snapshot
"""

import argparse
import glob
import os
import logging as log
import re
import stat
import socket
import subprocess
import sys
import shutil
import tarfile
import time
from multiprocessing.pool import ThreadPool

now = time.time()
progname = os.path.basename(__file__).replace('.py', '')

###############################################################################
#    Parse Comandline Options
###############################################################################

parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='store_true',
                    help='increase output verbosity')
parser.add_argument('-b', '--backup-dir', default='/backup',
                    help='Backup file location (default=/backup'
                    )
parser.add_argument('-c', '--compress', action='store_true',
                    help='compress backpu file')
parser.add_argument('-f', '--file-system', default='/data',
                    help='Filesystem mount (default=/data)')
parser.add_argument('-l', '--logical-volume', default='lv_data',
                    help='Logical Volume to Snap (default=lv_data)')
parser.add_argument('-m', '--mount', default='/tmp/snap_backup',
                    help='Location to mount snapshot (default=/tmp/snap_backup)')
parser.add_argument('-r', '--retention_days', default=3,
                    help='# Days to retain backups (default = 3)')
parser.add_argument('-s', '--snap-name', default='lv_data_snap',
                    help='Snapshot name (default=lv_data_snap)')
parser.add_argument('--log-dir', default='/var/log/%s' % progname,
                    help='Log file location (default=/var/log/%s)' % progname
                    )
args = parser.parse_args()

###############################################################################
#    Routine to verify file/directory exists
###############################################################################


def verify_file(f):
    if not os.path.exists(f):
        try:
            os.makedirs(f)

        except Exception as e:
            log.error('Could not create directory %s; exiting (%s)' % (f, e))
            sys.exit(2)


###############################################################################
#    Routine to verify lvm directory exists and has space
###############################################################################


def verify_lv(logical_volume, fs):
    run_cmd = ('du -sm %s' % fs)
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    data = data.split()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    used = int(data[0])
    run_cmd = ('lvs --noheadings --units b --separator \',\'')
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    for lv in data.split('\n'):
        lvinfo = lv.split(',')
        lvinfo = [field.replace("'", "").strip() for field in lvinfo]
        if lvinfo[0] == logical_volume:
            vg = lvinfo[1]

    run_cmd = 'vgs --noheadings --units b -o name,size,free %s' % vg
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    data = data.split()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    lv = data[0]
    vtotal = int(data[1].replace('B', ''))
    vfree = int(data[2].replace('B', ''))
    avail = (vtotal - vfree) / 1024 / 1024
    vneed = int(used * 1.2)
    log.debug(' LVM Space: %0.2fMB avail; need %0.2fMB' % (avail, vneed))
    if (avail < vneed):
        log.error('Insufficient LVM Space: %0.2fMB avail; need %0.2fMB' % (avail,
                                                                           vneed))
        exit(1)
    return(lv, vg, vneed)


###############################################################################
#    Routine to create lvm snapshot
###############################################################################

def snapit(vg, size):
    run_cmd = ('lvcreate --size %dM --snapshot --name %s %s/%s' % (size,
                                                                   args.snap_name,
                                                                   vg,
                                                                   args.logical_volume))
    log.debug('Running: %s' % run_cmd)
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    for line in data.split('\n'):
        log.debug('lvcreate: %s' % line)
    run_cmd = 'vgs --noheadings -o lv_name,lv_path %s' % vg
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    for lv in data.split('\n'):
        lvinfo = lv.split()
        if lvinfo[0] == args.snap_name:
            device_name = lvinfo[1]
            return(device_name)
    return(device_name)


###############################################################################
#    Routine to mount lvm snapshot
###############################################################################

def mountit(device, mount):
    run_cmd = ('mount -o nouuid %s %s' % (device, mount))
    log.debug('Running: %s' % run_cmd)
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    for line in data:
        log.debug('mount: %s' % line)
    return()


###############################################################################
#    Routine to unmount lvm snapshot
###############################################################################

def unmountit(mount):
    run_cmd = ('umount %s' % mount)
    log.debug('Running: %s' % run_cmd)
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    for line in data:
        log.debug('unmount: %s' % line)
    return()


###############################################################################
#    Routine to remove lvm snapshot
###############################################################################

def removeit(logical_volume, vg):
    run_cmd = 'lvs --noheadings -o lv_name,snap_percent %s' % vg
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    valid_snap = False
    for lv in data.split('\n'):
        lvinfo = lv.split()
        if (args.snap_name in lvinfo) and len(lvinfo) > 1:
            valid_snap = True
    if not valid_snap:
        return(False)
    run_cmd = ('lvremove -f %s' % (logical_volume))
    log.debug('Running: %s' % run_cmd)
    cmd = subprocess.Popen(run_cmd.split(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    data, err = cmd.communicate()
    rc = cmd.wait()
    if rc > 0:
        log.error('%s failed with %d: %s' % (run_cmd, rc, err))
    for line in data.split('\n'):
        log.debug('lvremove: %s' % line)
    return(True)

###############################################################################
#    Routine to backup snapshot
###############################################################################


def backsnap(backup_dir):
    cur_dir = os.getcwd()
    os.chdir(backup_dir)
    os.chdir('..')
    new_dir = os.getcwd()
    relative_dir = os.path.basename(backup_dir)
    log.debug('Backing up ./%s snapshot to: %s from %s' % (relative_dir,
                                                           backup_file,
                                                           new_dir))
    if args.compress:
        try:
            with tarfile.open('%s' % backup_file, "w:gz") as tar:
                tar.add(relative_dir)

        except Exception, e:
            log.error(e)
            log.error('Could not create backup %s (%s)') % (backup_file, e)
            sys.exit(2)
    else:
        try:
            with tarfile.open('%s' % backup_file, "w") as tar:
                tar.add(relative_dir)

        except Exception, e:
            log.error('Could not create backup. %s (%s)') % (backup_file, e)
            log.error(e)
            os.chdir(cur_dir)
            sys.exit(2)
    os.chdir(cur_dir)
    return()


###############################################################################
#    Setup Logging Options
###############################################################################

full_backup_dir = '%s/%s' % (args.backup_dir, socket.gethostname())
ext=".tar"
if args.compress:
    ext=".tar.gz"
backup_file = '%s/%s%s.%s%s' % (full_backup_dir,
                                  socket.gethostname(),
                                  args.file_system.replace('/', '_'),
                                  time.strftime('%Y-%m-%d:%H:%M:%S'),
                                  ext)
max_retention = 86400 * args.retention_days
verify_file(args.log_dir)

baselevel = log.INFO

if args.verbose:
    baselevel = log.DEBUG

os.path.basename(__file__)
log.basicConfig(filename='%s/%s.log' % (args.log_dir, progname),
                format='%(asctime)s %(levelname)s: %(message)s',
                level=baselevel)

# Log to console as well

formatter = log.Formatter('%(levelname)s: %(message)s')

console = log.StreamHandler()
console.setLevel(baselevel)
console.setFormatter(formatter)

log.getLogger('').addHandler(console)

log.info('******** Starting Backup *********')
log.info('Backing up: %s to %s' % (args.logical_volume,

###############################################################################
#    __Main__
###############################################################################

verify_file(full_backup_dir)
verify_file(args.mount)
log.debug('Verifying Snapshot Space')
(snap_lv, snap_vg, snap_size) = verify_lv(args.logical_volume, args.file_system)
log.debug('Creating Snapshot (%s, %d)' % (snap_lv, snap_size))
snap_device = snapit(snap_vg, snap_size)
log.info('======= LVM Snapshot Complete ========')

###############################################################################
#    Tar and compress backup(s)
###############################################################################

mountit(snap_device, args.mount)
log.debug('Tar & Gzipping backup')
backsnap(args.mount)
unmountit(args.mount)

###############################################################################
#    Chown & Chmod files so that they are accessible by other services
###############################################################################

log.debug('Updating backup file permissions')

for backup in sorted(glob.glob("%s/*" % full_backup_dir)):
    os.chmod("%s" % backup, stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH)
    os.chown("%s" % backup, 0, 4)

###############################################################################
#    Remove snapshot
###############################################################################

log.debug('Removing snapshot')
if (removeit(snap_device, snap_vg)):
    log.debug('Snapshot %s removed' % snap_device)
else:
    log.debug('Snapshot %s does not appear to be valid' % snap_device)

###############################################################################
#    Remove old backups
###############################################################################

log.debug('Removing snapshot backups older than %s' % args.retention_days)
for files in sorted(glob.glob("%s/%s%s.*.tar.*" % (full_backup_dir,
                                                   socket.gethostname(),
                                                   args.file_system.replace('/', '_')))):
    if os.path.isfile(files):
        if (now - max_retention) > os.path.getmtime(files):
            try:
                log.info(" - removing %s", files)
                # shutil.rmtree(my_dir)

            except Exception, e:
                log.error('Could not remove %s.') % files
                log.error(e)
                sys.exit(2)

log.info('======= LVM Backup Complete ========')
