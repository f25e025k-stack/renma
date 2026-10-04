#!/usr/bin/env python3
"""Read-only evidence collector for the legacy LVI-SAM + color map folder.

Walks SOURCE recursively, never writes inside it, and produces in OUT:

  FILE_INVENTORY.csv   every file: path, ext, size, mtime, category, relevance
  HITS.csv             keyword hits (file, line, key, text) in text-like files
  extracted/           verbatim copies of small high-value text files
                       (+ plain-text dumps of docx/pptx/xlsx), same relative paths
  IMAGES.csv           image list with dimensions-free metadata (images are not copied)
  SUMMARY.txt          counts per category/extension, run parameters
  legacy_audit_bundle.zip  everything above, for upload to the analysis session

Only the Python standard library is used. Nothing is executed from SOURCE.

Usage (Windows, from a lab PC that can see the share):
  py collect_legacy_evidence.py ^
     "\\\\CoastalEngLab2\\public\\個人フォルダ\\平野錬磨\\LiDAR_開発_LVI SAM+color map\\LVI SAM+color map" ^
     C:\\temp\\LEGACY_LVISAM_AUDIT_OUT
"""
import argparse
import csv
import datetime as dt
import os
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

TEXT_EXT = {
    ".md", ".txt", ".rst", ".yaml", ".yml", ".json", ".xml", ".launch", ".py",
    ".cpp", ".cc", ".c", ".h", ".hpp", ".sh", ".bash", ".cmake", ".csv", ".ini",
    ".cfg", ".conf", ".log", ".rviz", ".urdf", ".xacro", ".msg", ".srv", ".m",
    ".ipynb", ".bat", ".ps1", ".toml", ".pcd_header",
}
OFFICE_EXT = {".docx", ".pptx", ".xlsx"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif", ".webp"}
BIG_DATA_EXT = {".bag", ".db3", ".mcap", ".pcd", ".ply", ".las", ".laz", ".mp4",
                ".avi", ".mov", ".mkv", ".zip", ".tar", ".gz", ".7z", ".so", ".a",
                ".o", ".exe", ".dll", ".bin"}

MAX_TEXT_SCAN = 5 * 1024 * 1024      # scan text files up to 5 MB
MAX_COPY = 512 * 1024                # copy high-value text files up to 512 KB
MAX_LINE = 400

CATEGORY_RULES = [  # (category, regex on lowercase relative path)
    ("intrinsic", r"intrinsic|camera_calib|calib.*cam|cam.*calib|ost\.|camera_info|checker|chess"),
    ("extrinsic", r"extrinsic|lidar.?cam|cam.?lidar|t_lidar|t_cam|autoware|livox_camera|direct_visual_lidar"),
    ("calibration", r"calib|kalibr"),
    ("lvi-sam", r"lvi|lio.?sam|vins|params_camera|params_lidar"),
    ("colorization", r"color|colour|rgb|project|paint|fusion"),
    ("pcd", r"\.pcd$|pcd|save_map|map_save"),
    ("sync", r"sync|stamp|time|offset"),
    ("rosbag", r"\.bag$|\.db3$|\.mcap$|rosbag|record"),
    ("camera", r"camera|usb_cam|v4l|uvc|image"),
    ("lidar", r"ouster|os0|os1|velodyne|lidar"),
    ("mechanical", r"mount|bracket|cad|\.step$|\.stp$|\.stl$|\.dxf$|fixture|jig"),
    ("report", r"\.pdf$|\.docx?$|\.pptx?$|report|memo|readme|note|手順|報告|メモ"),
]
STATE_RULES = [
    ("failed", r"fail|ng|error|bad|broken|失敗"),
    ("success", r"success|final|ok|good|best|成功|完成"),
    ("backup", r"old|backup|bak|orig|copy|test|tmp|旧|バックアップ"),
]

HIT_PATTERNS = {
    # intrinsic / detector
    "detector": r"findChessboardCorners(SB)?|findCirclesGrid|aruco|charuco|apriltag|detectMarkers",
    "detector_flags": r"CALIB_CB_[A-Z_]+",
    "subpix": r"cornerSubPix|TermCriteria|TERM_CRITERIA",
    "calib_api": r"calibrateCamera(Extended|RO)?|fisheye\.calibrate|omnidir|stereoCalibrate|camera_calibration|cameracalibrator",
    "calib_flags": r"CALIB_(?!CB_)[A-Z_0-9]+|fisheye\.CALIB_[A-Z_]+",
    "board_geom": r"square[_ ]?size|--size|--square|board[_ ]?(size|rows|cols|width|height)|pattern[_ ]?size|8x6|9x7|8x5|9x6|7x5|inner",
    "camera_model": r"distortion_model|plumb_bob|rational_polynomial|equidistant|kannala|pinhole|model_type|MEI|camera_model",
    "intrinsic_values": r"camera_matrix|distortion_coefficients|projection_matrix|rectification_matrix|\bfx\b|\bfy\b|\bcx\b|\bcy\b|\bk1\b|\bk2\b|\bp1\b|\bp2\b|\bk3\b|\bmu\b|\bmv\b|\bu0\b|\bv0\b|\bxi\b",
    "resolution": r"image_width|image_height|\bwidth\b|\bheight\b|\d{3,4}\s*[x×]\s*\d{3,4}",
    "reproj_error": r"reprojection|rms|re-?projection|projection error|per.?view|holdout|validation",
    "camera_controls": r"focus|autofocus|zoom|exposure|gain|white_balance|wb_|v4l2-ctl|pixel_format|mjpeg|yuyv|framerate|fps",
    # extrinsic
    "extrinsic_keys": r"extrinsic(Rot|RPY|Trans|_rotation|_translation)?|T_lidar|T_cam|lidar_to_cam|cam_to_lidar|camera_to_lidar|lidar_to_camera|static_transform_publisher|tf2?|base_link|frame_id|child_frame",
    "extrinsic_method": r"solvePnP|PnP|ransac|plane|edge|ceres|optimi[sz]|levenberg|gauss.?newton|icp|ndt|calibration_tool|autoware|lidar_camera_calib|livox|direct_visual_lidar|kalibr",
    # sync
    "sync": r"ApproximateTime|ExactTime|message_filters|header\.stamp|ros::Time|rclcpp::Time|use_sim_time|time_?offset|timeshift|td\b|estimate_td|latency|ptp|gps|pps|sync",
    # colorization / projection
    "projection": r"projectPoints|undistort(Points)?|initUndistortRectifyMap|remap\(|cv::Mat K|intrinsic.*\*|uv\b|\bu\s*=|\bv\s*=|in_image|inside image|bounds",
    "occlusion": r"z.?buffer|depth.?buffer|occlu|visib|hidden|nearest|closest",
    "fusion": r"blend|average|weight|multi.?view|accumulate|vote|median",
    # pcd
    "pcd_io": r"PointXYZRGB|PointXYZI|PointXYZRGBA|savePCDFile(ASCII|Binary|BinaryCompressed)?|pcl::io|PCDWriter|loadPCDFile|binary_compressed|open3d|write_point_cloud|FIELDS|SIZE|TYPE|COUNT|DATA ascii|DATA binary",
    "pcd_fields": r"intensity|ring|\btime\b|\bt\b|reflectivity|ambient|range|rgb",
    # topics
    "topics": r"/[a-zA-Z_][\w/]*(image|points|imu|camera_info|cloud)[\w/]*",
}
COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in HIT_PATTERNS.items()}

HIGH_VALUE_COPY = re.compile(
    r"calib|intrinsic|extrinsic|camera|params|config|\.ya?ml$|\.launch|readme|\.md$|"
    r"color|project|fusion|pcd|sync|memo|note|log|手順|メモ|\.txt$|\.json$",
    re.IGNORECASE,
)


def classify(rel_lower):
    cats = [c for c, rx in CATEGORY_RULES if re.search(rx, rel_lower)]
    states = [s for s, rx in STATE_RULES if re.search(rx, rel_lower)]
    return ";".join(cats) or "unknown", ";".join(states)


def relevance(ext, cats, size):
    if ext in BIG_DATA_EXT:
        return "metadata-only"
    if ext in TEXT_EXT | OFFICE_EXT or ext == ".pdf":
        return "high" if cats != "unknown" else "medium"
    if ext in IMAGE_EXT:
        return "medium" if cats != "unknown" else "low"
    return "low"


def read_text(path):
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp932", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1"


def office_text(path):
    """Extract plain text from docx/pptx/xlsx via zip+regex (stdlib only)."""
    out = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if n.endswith(".xml") and (
                           n.startswith("word/document") or n.startswith("ppt/slides/slide")
                           or n.startswith("ppt/notesSlides/") or n == "xl/sharedStrings.xml"
                           or n.startswith("xl/worksheets/sheet")))
        for n in names:
            xml = z.read(n).decode("utf-8", errors="replace")
            xml = re.sub(r"</(w:p|a:p|row)>", "\n", xml)
            txt = re.sub(r"<[^>]+>", " ", xml)
            txt = re.sub(r"[ \t]+", " ", txt)
            out.append(f"===== {n} =====\n{txt.strip()}\n")
    return "\n".join(out)


def scan_lines(text, rel, writer):
    n = 0
    for i, line in enumerate(text.splitlines(), 1):
        for key, rx in COMPILED.items():
            if rx.search(line):
                writer.writerow([rel, i, key, line.strip()[:MAX_LINE]])
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("out")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    out = Path(args.out).resolve()
    if not src.is_dir():
        sys.exit(f"source not found: {src}")
    if out == src or src in out.parents:
        sys.exit("refusing: output directory must be OUTSIDE the source folder")
    out.mkdir(parents=True, exist_ok=True)
    ext_dir = out / "extracted"

    ext_count, cat_count = Counter(), Counter()
    errors = []
    with open(out / "FILE_INVENTORY.csv", "w", newline="", encoding="utf-8-sig") as finv, \
         open(out / "HITS.csv", "w", newline="", encoding="utf-8-sig") as fhit, \
         open(out / "IMAGES.csv", "w", newline="", encoding="utf-8-sig") as fimg:
        inv, hit, img = csv.writer(finv), csv.writer(fhit), csv.writer(fimg)
        inv.writerow(["path", "ext", "size_bytes", "modified_local", "category", "state_hint",
                      "relevance", "scanned", "copied", "hit_count"])
        hit.writerow(["path", "line", "key", "text"])
        img.writerow(["path", "size_bytes", "modified_local", "category"])

        for root, dirs, files in os.walk(src):
            dirs.sort()
            for name in sorted(files):
                p = Path(root) / name
                rel = p.relative_to(src).as_posix()
                try:
                    st = p.stat()
                except OSError as e:
                    errors.append(f"stat {rel}: {e}")
                    continue
                ext = p.suffix.lower()
                cats, states = classify(rel.lower())
                rel_lvl = relevance(ext, cats, st.st_size)
                mtime = dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
                scanned = copied = False
                nhits = 0
                try:
                    if ext in TEXT_EXT and st.st_size <= MAX_TEXT_SCAN:
                        text, _ = read_text(p)
                        nhits = scan_lines(text, rel, hit)
                        scanned = True
                        if st.st_size <= MAX_COPY and (HIGH_VALUE_COPY.search(rel) or nhits):
                            dst = ext_dir / rel
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(p, dst)  # copy2 avoided: no metadata writes needed
                            copied = True
                    elif ext in OFFICE_EXT and st.st_size <= 50 * MAX_TEXT_SCAN:
                        text = office_text(p)
                        nhits = scan_lines(text, rel, hit)
                        scanned = True
                        dst = ext_dir / (rel + ".txt")
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_text(text, encoding="utf-8")
                        copied = True
                    elif ext == ".pdf" and st.st_size <= 20 * 1024 * 1024:
                        dst = ext_dir / rel  # PDFs copied for later text extraction
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(p, dst)
                        copied = True
                    elif ext == ".pcd":
                        # header only (first 11 lines), never the payload
                        with open(p, "rb") as f:
                            head = b"".join(f.readline() for _ in range(11))
                        dst = ext_dir / (rel + ".header.txt")
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_bytes(head)
                        copied = True
                except Exception as e:  # keep walking; record the failure
                    errors.append(f"read {rel}: {e}")
                if ext in IMAGE_EXT:
                    img.writerow([rel, st.st_size, mtime, cats])
                inv.writerow([rel, ext, st.st_size, mtime, cats, states, rel_lvl,
                              scanned, copied, nhits])
                ext_count[ext or "(none)"] += 1
                for c in cats.split(";"):
                    cat_count[c] += 1

    with open(out / "SUMMARY.txt", "w", encoding="utf-8") as f:
        f.write(f"source: {src}\nrun_at: {dt.datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"python: {sys.version.split()[0]}\nfiles: {sum(ext_count.values())}\n\n")
        f.write("[by extension]\n" + "".join(f"{k}\t{v}\n" for k, v in ext_count.most_common()))
        f.write("\n[by category]\n" + "".join(f"{k}\t{v}\n" for k, v in cat_count.most_common()))
        f.write("\n[errors]\n" + "\n".join(errors) + "\n")

    bundle = out / "legacy_audit_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file() and p != bundle:
                z.write(p, p.relative_to(out).as_posix())
    print(f"done: {sum(ext_count.values())} files, errors={len(errors)}\nbundle: {bundle}")


if __name__ == "__main__":
    main()
