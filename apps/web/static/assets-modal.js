// assets-modal.js — bench 页的 "编辑资产" modal.
//
// 职责: 让用户编辑 polaroid 的所有 asset (role / captured_at / device),
// 不能增删 path (增删走 import / append / 后续单独入口).
// 提交到 POST /bench/{pid}/save-assets.

(function () {
  'use strict';

  function assetsModal(pid, initial) {
    return {
      pid: pid,
      open: false,
      saving: false,
      errorMsg: '',
      // 深拷贝 initial, 避免修改页面原数据
      assets: JSON.parse(JSON.stringify(initial)),

      openModal() { this.open = true; this.errorMsg = ''; },
      closeModal() { this.open = false; this.errorMsg = ''; },

      moveUp(i) {
        if (i <= 0) return;
        const tmp = this.assets[i - 1];
        this.assets[i - 1] = this.assets[i];
        this.assets[i] = tmp;
      },
      moveDown(i) {
        if (i >= this.assets.length - 1) return;
        const tmp = this.assets[i + 1];
        this.assets[i + 1] = this.assets[i];
        this.assets[i] = tmp;
      },

      async save() {
        // 校验
        for (const a of this.assets) {
          if (!a.path || !String(a.path).trim()) {
            this.errorMsg = '每行必须有 path';
            return;
          }
        }
        this.saving = true;
        this.errorMsg = '';
        try {
          const r = await fetch('/bench/' + encodeURIComponent(this.pid) + '/save-assets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              assets: this.assets.map(a => ({
                role: a.role || 'front',
                path: String(a.path).trim(),
                captured_at: a.captured_at || null,
                device: a.device || null,
              })),
            }),
          });
          if (!r.ok) {
            const t = await r.text();
            throw new Error('HTTP ' + r.status + ' - ' + t);
          }
          // 成功, 关闭并刷新
          this.open = false;
          window.location.reload();
        } catch (e) {
          this.errorMsg = e.message || String(e);
        } finally {
          this.saving = false;
        }
      },
    };
  }

  window.assetsModal = assetsModal;
})();