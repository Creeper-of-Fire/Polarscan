// path-parse.js — 从文件夹名 / 文件名推断拍摄日期段.
//
// 用户约定 (与 _bootstrap.py path_slug 一致):
//   - 子文件夹名形如 "2026.07.25-26" 或 "2026-07-25-26"
//   - 文件名形如 "img20260725_17185555_xxxxxx.png" (扫描时间戳)
//
// 用途:
//   - /new 页 drop 后, 从 F:盘路径的父目录名推断日期段, 给 shot_date 候选
//   - /bench 页 drop 后, 提示用户当前 polaroid 日期与文件日期是否一致
//
// 函数:
//   parseFolderDateRange(name) -> {start: 'YYYY-MM-DD', end: 'YYYY-MM-DD'} | null
//   parseFilenameDate(name)    -> 'YYYY-MM-DD' | null  (扫描日期, 不是拍摄日期)

(function () {
  'use strict';

  // 匹配 2026.07.25-26 / 2026.07.25-2026.07.27 / 2026-07-25
  // 接受 . 或 - 作为分隔符
  const RANGE_RE = /^(\d{4})[\.\-](\d{1,2})[\.\-](\d{1,2})(?:[-](\d{1,2})(?:[\.\-](\d{1,2}))?)?$/;

  // 匹配 2026.07.25 / 2026-7-5
  const SINGLE_RE = /^(\d{4})[\.\-](\d{1,2})[\.\-](\d{1,2})$/;

  function pad2(n) { return String(n).padStart(2, '0'); }

  function toIso(year, month, day) {
    const y = String(year);
    const m = pad2(month);
    const d = pad2(day);
    // 简单合法性检查 (允许 02-29 在闰年等细节由 Date 处理)
    const dt = new Date(y + '-' + m + '-' + d + 'T00:00:00');
    if (isNaN(dt.getTime())) return null;
    return y + '-' + m + '-' + d;
  }

  function parseFolderDateRange(name) {
    const m = RANGE_RE.exec(name);
    if (!m) return null;
    const year = parseInt(m[1], 10);
    const startMonth = parseInt(m[2], 10);
    const startDay = parseInt(m[3], 10);

    const startIso = toIso(year, startMonth, startDay);
    if (!startIso) return null;

    let endIso = startIso;
    if (m[4]) {
      // 形如 2026.07.25-26 (同月范围)
      const endDay = parseInt(m[4], 10);
      endIso = toIso(year, startMonth, endDay);
      if (!endIso) return null;
    } else if (m[5]) {
      // 形如 2026.07.25-08.02 (跨月范围) — 这里简化, 不解析
      return null;
    }
    return { start: startIso, end: endIso };
  }

  // 文件名: imgYYYYMMDD_HHMMSSxx_xxxxxx.png
  const FN_DATE_RE = /^img(\d{4})(\d{2})(\d{2})_/i;

  function parseFilenameDate(name) {
    const m = FN_DATE_RE.exec(name);
    if (!m) return null;
    return m[1] + '-' + m[2] + '-' + m[3];
  }

  // 从 file.path 推导父目录名
  function parentDirName(path) {
    if (!path) return null;
    // 接受 Windows 和 POSIX 分隔符
    const parts = String(path).split(/[\\/]/);
    if (parts.length < 2) return null;
    return parts[parts.length - 2];
  }

  // 公开 API
  window.PathParse = {
    parseFolderDateRange: parseFolderDateRange,
    parseFilenameDate: parseFilenameDate,
    parentDirName: parentDirName,
  };
})();