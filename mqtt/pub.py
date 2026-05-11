"""
Point machine telemetry publisher (RDPMS FRS-aligned) with fault injection
and 3-class predictive-maintenance labels.

Published parameters (15 FRS values + 2 ML metadata fields):
  vpt_nwkr, vpt_rwkr           — 24 V detection feeds at relay room
  nwkr, rwkr, nwcr, rwcr       — digital relay states
  vpt_110_n, vpt_110_r         — 110 V supply at location box
  ipt_n, ipt_r                 — motor currents (Normal / Reverse)
  vpt_24_n, vpt_24_r           — 24 V at LOC after detection
  vib_x                        — vibration X
  tpt_n, tpt_r                 — derived stroke times
  fault                        — name of currently active fault, "" if none
  label                        — NORMAL | MAINTENANCE_ALERT | FAULT

Each fault has two phases:
  PRECURSOR (10-18 s)  — slow drift of relevant parameters into the FRS
                         min_safe warning band. Labelled MAINTENANCE_ALERT.
  ACTIVE   (3-20 s)    — parameter pushed past min_fail / abnormal range.
                         Labelled FAULT.

This gives a supervised ML dataset with leading indicators before each fault,
which is what predictive maintenance models need to learn.

Faults injected:
  LOW_VPT_NWKR     — 24 V detection feed sags (battery / wire degradation)
  LOW_VPT_110      — 110 V supply dip
  OBSTRUCTION      — stroke runs longer than max_safe TPT (8 s); current
                     stays elevated until forced clear
  OVER_CURRENT     — abnormally high motor current during stroke
  VIB_SPIKE        — abnormal vibration
  PHANTOM_CURRENT  — small idle current (leakage / hot wire)
  STUCK_NWKR_DROP  — NWKR position relay fails to pick up at Normal
"""

from publisher.main import run

if __name__ == "__main__":
    run()
