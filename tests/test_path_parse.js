// path-parse.js 的最小 node 测试
const fs = require('fs');
const path = require('path');

// 加载 path-parse.js (它在 IIFE 里, 注册到 window; 在 node 里手动 mock window)
global.window = {};
require(path.join(__dirname, '..', 'apps', 'web', 'static', 'path-parse.js'));

const P = global.window.PathParse;
if (!P) { console.error('PathParse not registered'); process.exit(1); }

let failed = 0;
function check(label, actual, expected) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a === e) {
    console.log('  ok:', label);
  } else {
    console.log('FAIL:', label, '\n   expected:', e, '\n     actual:', a);
    failed++;
  }
}

// parseFolderDateRange
console.log('parseFolderDateRange:');
check('点分隔单日',     P.parseFolderDateRange('2026.07.25'), { start: '2026-07-25', end: '2026-07-25' });
check('横线分隔单日',    P.parseFolderDateRange('2026-07-25'), { start: '2026-07-25', end: '2026-07-25' });
check('点分隔同月范围',  P.parseFolderDateRange('2026.07.25-26'), { start: '2026-07-25', end: '2026-07-26' });
check('点分隔跨日范围',  P.parseFolderDateRange('2026.07.25-2026.07.27'), null);  // 不解析跨月
check('不匹配',         P.parseFolderDateRange('已喂狗'), null);
check('不匹配',         P.parseFolderDateRange('random_folder'), null);

// parseFilenameDate
console.log('parseFilenameDate:');
check('标准文件名',      P.parseFilenameDate('img20260804_120000_aabbcc.png'), '2026-08-04');
check('大小写不敏感',    P.parseFilenameDate('IMG20260804_120000_aabbcc.PNG'), '2026-08-04');
check('非匹配',         P.parseFilenameDate('photo.jpg'), null);

// parentDirName
console.log('parentDirName:');
check('Windows 路径',   P.parentDirName('F:\\相册\\2026.07.25\\img.png'), '2026.07.25');
check('POSIX 路径',     P.parentDirName('/photos/2026.07.25/img.png'), '2026.07.25');
check('无父目录',       P.parentDirName('img.png'), null);

if (failed > 0) {
  console.error('\n' + failed + ' test(s) failed');
  process.exit(1);
} else {
  console.log('\nall ok');
}