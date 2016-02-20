
Documentation about PySnap

====

The PySnap LVM backup process uses snaphots for backups:
 - Creates a snapshot of a logical volume
 - Temporarily mounts the snapshot
 - Uses tar to back up the mounted snapshot
 - Drops the snapshot

Files
----

- py_snap.py:       ``` python backup script ```

Installation Requirements
----

- Python 2.7
- Must run as root or have privs via sudo

PySnap Instructions
----

The py_snap.py process use lmv commands to create snapshots and must have root or
 sudo privs.  There must be enough unallocated space in the volume group for the 
 snapshot(s) to be created or the process will exit without creating the backup.

By default, logs end up at /var/log/py_snap/py_snap.log, and backups can
 be found at ```/backup/<hostname>/```.  Old backups will be removed by default if 
 they are more than 3 days old.

Backups can be restored as followed:
- shutdown any process using files being replaced by backup (for example, mongodb)
- gunzip -c ```/backup/<hostname>/<hostname>_<fs>.<datestamp>.tar.gz|tar -xvf - <extract directory>```
- remove any required pid or lock files from <extract directory>/snap_backup ( for example, mongod.lock )
- copy all files from ```<extract directory>/snap_backup``` to the target directory
- startup any processes using the restore files (for example, mongodb)
- remove ```<extract directory>/snap_backup```

PySnap Options
----

```
usage: py_snap.py [-h] [-v] [-b BACKUP_DIR] [-c] [-f FILE_SYSTEM]
                     [-l LOGICAL_VOLUME] [-m MOUNT] [-r RETENTION_DAYS]
                     [-s SNAP_NAME] [--log-dir LOG_DIR]

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         increase output verbosity
  -b BACKUP_DIR, --backup-dir BACKUP_DIR
                        Backup file location (default=/backup
  -c, --compress        compress backpu file
  -f FILE_SYSTEM, --file-system FILE_SYSTEM
                        Filesystem mount (default=/data)
  -l LOGICAL_VOLUME, --logical-volume LOGICAL_VOLUME
                        Logical Volume to Snap (default=lv_data)
  -m MOUNT, --mount MOUNT
                        Location to mount snapshot (default=/tmp/snap_backup)
  -r RETENTION_DAYS, --retention_days RETENTION_DAYS
                        # Days to retain backups (default = 3)
  -s SNAP_NAME, --snap-name SNAP_NAME
                        Snapshot name (default=lv_data_snap)
  --log-dir LOG_DIR     Log file location (default=/var/log/lvm_backup)

```
