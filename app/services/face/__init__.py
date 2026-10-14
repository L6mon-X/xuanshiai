"""人脸认证适配器（D-14）。

背景：`get_face_verified_user` 门禁已被社区发帖使用（`routes/community.py`），
但全仓没有任何人脸服务适配层，`face_verified` 只能由后台人工审核写入。
本模块提供统一接口与 mock / disabled 实现，真实供应商接入留待上线门禁
（见 docs/全项目后端详细修改方案清单-2026-10-12.md 第七节）。
"""
