// drop.js — /new 与 /bench 页的拖入工作流。
//
// 通过 Alpine x-data 工厂函数对外暴露：
//   - createFromFiles(): /new 页用, 拖入 → identify → 新建 polaroid
//   - appendToPid(pid): /bench 页用, 拖入 → identify → append 到现有 polaroid
//
// 依赖（base.html 已通过 CDN 引入）：
//   - Alpine.js (window.Alpine)
//   - blakejs (window.blake2bHex)
//   - /api/drop/identify 端点

(function () {
  'use strict';

  // ============================================================
  // 工具函数
  // ============================================================

  // 读一次 arrayBuffer, 同时算 hash + 生成 data URL (缩略图)
  // 避免 FileReader + arrayBuffer 读两次文件
  async function readFileData(file) {
    const buf = await file.arrayBuffer();
    const bytes = new Uint8Array(buf);
    const hash = await hashwasm.blake2b(bytes, 512);
    // base64 encode for thumbnail data URL
    let binary = '';
    const chunk = 0x8000;  // avoid call stack overflow on large files
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    const dataUrl = 'data:image/png;base64,' + btoa(binary);
    return { hash, dataUrl };
  }

  // File.lastModified 是 epoch 毫秒, server Triple.mtime 是整数 epoch 秒
  function fileMtimeSeconds(file) {
    return Math.round(file.lastModified / 1000);
  }

  // 调用 /api/drop/identify
  async function callIdentify(item) {
    const r = await fetch('/api/drop/identify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: item.name,
        size: item.size,
        lastModified_ms: item.mtime * 1000,
        hash: item.hash,
      }),
    });
    if (!r.ok) throw new Error('identify 失败: HTTP ' + r.status);
    return r.json();
  }

  // 默认 role 规则: front=1st, back=2nd, 其余 additional
  function defaultRole(index) {
    if (index === 0) return 'front';
    if (index === 1) return 'back';
    return 'additional';
  }

  // ============================================================
  // /new 页: create-from-files
  // ============================================================

  function createFromFiles() {
    return {
      // ---- 状态 ----
      files: [],          // [{ name, size, mtime, hash, identify: { by_hash, candidates } }]
      status: 'idle',     // idle | hashing | identifying | ready | submitting | error
      errorMsg: '',

      // ---- 表单字段 (双向绑定到现有 input) ----
      // shotDate 由外部 form 提供 (input[name=shot_date]), 用 getter 引用

      // ---- 派生 ----
      get importable() {
        // 可导入的 (path, role), 跳过 hash 命中的文件
        const out = [];
        this.files.forEach((f, i) => {
          if (f.identify.by_hash.length > 0) return;
          const cand = (f.identify.candidates || [])[0];
          if (!cand) return;
          out.push({ path: cand.path, role: defaultRole(i) });
        });
        return out;
      },

      get hashHits() {
        return this.files.filter(f => f.identify.by_hash.length > 0);
      },

      get candidatesInYaml() {
        return this.files.filter(f =>
          f.identify.by_hash.length === 0 &&
          (f.identify.candidates || []).some(c => c.in_yaml_pid)
        );
      },

      get newFiles() {
        return this.files.filter(f =>
          f.identify.by_hash.length === 0 &&
          !(f.identify.candidates || []).some(c => c.in_yaml_pid) &&
          (f.identify.candidates || []).length > 0
        );
      },

      // 从候选路径的父目录名推断日期段 (单一结果, 取第一个能解析的)
      get dateSuggestion() {
        const tryFromFiles = (candidates) => {
          for (const cand of candidates) {
            const dirName = window.PathParse.parentDirName(cand.path);
            if (!dirName) continue;
            const range = window.PathParse.parseFolderDateRange(dirName);
            if (range) return range;
          }
          return null;
        };
        // 优先从 importable 取
        const importablePaths = this.importable.map(i => ({ path: i.path }));
        return tryFromFiles(importablePaths)
          || tryFromFiles(this.files.flatMap(f => (f.identify.candidates || []).slice(0, 1)));
      },

      applyDate(date) {
        const shotInput = document.querySelector('input[name=shot_date]');
        if (shotInput) {
          shotInput.value = date;
          shotInput.dispatchEvent(new Event('input'));
        }
      },

      // ---- 操作 ----
      async handleDrop(event) {
        event.preventDefault();
        const dt = event.dataTransfer;
        if (!dt || !dt.files || dt.files.length === 0) return;

        this.status = 'hashing';
        this.errorMsg = '';
        this.files = [];

        const fileList = Array.from(dt.files);

        try {
          // 1) 算 hash + 缩略图 (一次 IO)
          const hashed = await Promise.all(fileList.map(async (f) => {
            const data = await readFileData(f);
            return {
              name: f.name,
              size: f.size,
              mtime: fileMtimeSeconds(f),
              hash: data.hash,
              thumb: data.dataUrl,
            };
          }));

          this.status = 'identifying';

          // 2) identify
          const identified = await Promise.all(hashed.map(async (h) => ({
            ...h,
            identify: await callIdentify(h),
          })));

          this.files = identified;
          this.status = 'ready';

          // 3) 自动填到下方表单 (asset_paths textarea + 可选 shot_date)
          this.populateForm();
        } catch (e) {
          this.errorMsg = e.message || String(e);
          this.status = 'error';
        }
      },

      // 把可导入的路径自动填到表单 (textarea 一行一个), 不覆盖用户已手动填的内容
      populateForm() {
        const paths = this.importable.map(i => i.path);
        if (paths.length === 0) return;

        const ta = document.getElementById('new_asset_paths');
        if (ta) {
          const existing = ta.value.split('\n').map(s => s.trim()).filter(Boolean);
          const merged = [...new Set([...existing, ...paths])];
          ta.value = merged.join('\n');
        }

        // 如果 shot_date 还没填且能从一个候选路径的父目录推断, 自动填第一个
        const shotInput = document.querySelector('input[name=shot_date]');
        if (shotInput && !shotInput.value.trim()) {
          for (const cand of paths) {
            const dirName = window.PathParse.parentDirName(cand);
            if (!dirName) continue;
            const range = window.PathParse.parseFolderDateRange(dirName);
            if (range) {
              shotInput.value = range.start;
              shotInput.dispatchEvent(new Event('input'));  // 触发 suggestId 重新派生 pid
              break;
            }
          }
        }
      },

      fileStatus(f) {
        if (f.identify.by_hash.length > 0) return 'hash-hit';
        const cands = f.identify.candidates || [];
        if (cands.some(c => c.in_yaml_pid)) return 'candidate-in-yaml';
        if (cands.length > 0) return 'new';
        return 'no-match';
      },

      fileStatusLabel(f) {
        const s = this.fileStatus(f);
        if (s === 'hash-hit') return '已存在 (hash 命中)';
        if (s === 'candidate-in-yaml') return 'F:盘找到, 已在库';
        if (s === 'new') return '新文件';
        return 'F:盘未找到';
      },

      firstCandidatePath(f) {
        const cands = f.identify.candidates || [];
        return cands[0] ? cands[0].path : null;
      },

      removeFile(i) {
        this.files.splice(i, 1);
        if (this.files.length === 0) this.status = 'idle';
      },

      reset() {
        this.files = [];
        this.status = 'idle';
        this.errorMsg = '';
      },
    };
  }

  // ============================================================
  // /bench 页: append-to-pid (Step 5 用, 先占位)
  // ============================================================

  function appendToPid(pid) {
    return {
      pid: pid,
      files: [],
      status: 'idle',
      errorMsg: '',

      async handleDrop(event) {
        event.preventDefault();
        const dt = event.dataTransfer;
        if (!dt || !dt.files || dt.files.length === 0) return;

        this.status = 'hashing';
        this.errorMsg = '';
        this.files = [];

        try {
          const hashed = await Promise.all(Array.from(dt.files).map(async (f) => ({
            name: f.name,
            size: f.size,
            mtime: fileMtimeSeconds(f),
            hash: await computeFileHash(f),
          })));
          this.status = 'identifying';
          const identified = await Promise.all(hashed.map(async (h) => ({
            ...h,
            identify: await callIdentify(h),
          })));
          this.files = identified;
          this.status = 'ready';
        } catch (e) {
          this.errorMsg = e.message || String(e);
          this.status = 'error';
        }
      },

      fileStatus(f) {
        if (f.identify.by_hash.length > 0) return 'hash-hit';
        const cands = f.identify.candidates || [];
        if (cands.some(c => c.in_yaml_pid)) return 'candidate-in-yaml';
        if (cands.length > 0) return 'new';
        return 'no-match';
      },

      fileStatusLabel(f) {
        const s = this.fileStatus(f);
        if (s === 'hash-hit') return '已存在';
        if (s === 'candidate-in-yaml') return '已在库';
        if (s === 'new') return '新';
        return '未找到';
      },

      async confirmAppend() {
        const items = [];
        this.files.forEach((f, i) => {
          if (f.identify.by_hash.length > 0) return;
          const cand = (f.identify.candidates || [])[0];
          if (!cand) return;
          items.push({ path: cand.path, role: defaultRole(this.files.indexOf(f) + 1) });
        });
        // role 起始 index 取决于现有 polaroid 的资产数 (这里简化, 全部追加)
        // server 端需根据现有 polaroid 的 assets 数算默认 role
        // 暂时全部用 "additional", 让用户在 modal 里调
        // 实际: 让 server 根据现有 assets 长度算 front/back/additional
        const paths = items.map(i => i.path);

        if (paths.length === 0) {
          this.errorMsg = '没有可追加的文件';
          this.status = 'error';
          return;
        }

        this.status = 'submitting';
        try {
          const r = await fetch('/api/polaroids/' + encodeURIComponent(this.pid) + '/append-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: paths }),
          });
          if (!r.ok) {
            const t = await r.text();
            throw new Error('追加失败: HTTP ' + r.status + ' - ' + t);
          }
          // 刷新当前 bench 页
          window.location.reload();
        } catch (e) {
          this.errorMsg = e.message || String(e);
          this.status = 'error';
        }
      },

      reset() {
        this.files = [];
        this.status = 'idle';
        this.errorMsg = '';
      },
    };
  }

  // ============================================================
  // 暴露到 window (Alpine 通过字符串名引用)
  // ============================================================
  window.createFromFiles = createFromFiles;
  window.appendToPid = appendToPid;
})();