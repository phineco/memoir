# 固定版本前端资源

ECharts 5.5.0（Apache-2.0）和 Quill 2.0.3（BSD-3-Clause）沿用项目当前版本，改由本站提供；许可证与 ECharts NOTICE 一同保留。原始来源和 SHA-256 见 `tools/frontend.lock.json`。

升级时先核对上游版本与许可证，替换文件、更新锁定校验值，再执行构建、Python 测试和 UI 回归。不要直接编辑 `static/dist/`；生产不访问第三方 CDN，也不需要 npm。
