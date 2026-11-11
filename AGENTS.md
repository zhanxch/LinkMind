# 项目记忆

开始讨论方案、论文或实验前，先读 [当前版本与证据](docs/current-status.md) 和 [项目规则](.cursor/rules/roborag-research.mdc)。

本分支汇总 8 个已完成评测的任务实现。已记录成绩属于原冻结候选，集成兼容测试不等于重新跑过原生评测。用户已要求收束这些任务实现；维护复现入口时保持任务提示、工具接口、动作和评分语义。

Foldclothes 复现与无检索消融入口为 [复现指南](docs/fold-clothes-reproduction.md)。保留原始结果、失败、中断、补测和来源哈希；未评分单列。不要修改原冻结工作树或根据新代码重生成原契约 fixture 来通过测试。

当前公开版本另见 [发布说明](docs/release.md)。论文主表遵循作者的来源与填零口径，与本地原生逐例结果分开。不得将论文、TeX、PDF、认证文件或运行机器配置加入公开仓库。更改发布表格时修改 `results/paper-main-table.json` 后运行 `scripts/build_public_results.py`，不要独立改生成表格。
