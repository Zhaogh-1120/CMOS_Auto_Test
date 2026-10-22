# GitHub 更新前操作步骤

## 1. 更新方式
建议先克隆原 GitHub 仓库或在当前仓库创建分支，**不要将 ZIP 中的父目录 `CMOS_Auto_Test-main` 再嵌套一层提交**。仅将新 ZIP 里该目录下面的内容覆盖到仓库根目录对应位置。

Windows CMD 参考：
```bat
git status
git switch -c feat/spi-register-read-enhancement
REM 使用文件管理器将新版 zip 内 CMOS_Auto_Test-main 下的内容合并至仓库根目录
git status --short
git diff --stat
git diff --check
```

提交前通过 `git diff` 检查真正变化的源码，尤其避免不必要地提交 `logs/`、`outputs/`、`__pycache__/` 和本机路径、凭据。

```bat
git add full_flow_test python_ginkgo_spi CHANGELOG.md
git diff --cached --stat
git commit -m "fix(spi): correct two-frame reads and enhance register CLI"
git push -u origin feat/spi-register-read-enhancement
```
上面 `CHANGELOG.md` 是建议在仓库根目录新建的文件名：可将 `CHANGELOG_20261022.md` 内容复制过去；如果已有 CHANGELOG，请合并该版本条目而不是覆盖历史。

## 2. 本地离线验证
```bat
cd full_flow_test
python -m unittest discover -s tests -p "test_*mock.py" -v
cd ..\python_ginkgo_spi
python -m unittest discover -s tests -p "test_*mock.py" -v
```
两边预期各有 33 个测试通过。Python 版本、依赖按照原工程与本机 Conda 环境配置。

## 3. 真实芯片回归（先安全后写入）
以下命令在 `full_flow_test` 下执行。**仅在经确认可写的寄存器上运行实际写入。**

```bat
python main.py read --reg 0x20
python main.py read --name REG20
python main.py read --name CFG_OSC2_IDAC_IBIAS
python main.py field-write --name CFG_OSC2_IDAC_IBIAS --value 0b01010 --dry-run
python main.py write --reg 0x20 --value 256
```
最后一条应报红色错误且不会写入。上述常规只读/预演命令会触发 SPI 读帧；不执行数据写入帧。

需要验证真正的 `write-read`、`field-write-read` 和扫描时，请先手工备份目标寄存器原值、确认安全设置和恢复步骤。目前 CLI 扫描结束不会自动恢复原配置，且校验 FAIL 后可能继续执行。

## 4. 审计问题作为独立修复清单
- P0: 非零退出码 + 扫描遇 FAIL 停止 + FullFlowRecord 汇总状态。
- P1: Field 完整 REG/可验证掩码比较；约束或禁用未同步 `--use-shadow`。
- P2: batch_write 预检查、SPI 初始化失败资源关闭、SPI 控制参数合法性、统一终点规则。

这些缺陷已在离线故障注入中重现，**尚未包含修复**。推荐建 GitHub Issues，独立修复并添加对应自动化回归测试。

## 5. 发布检查
- [ ] 比较已暂存文件，确认没有覆盖 GitHub 上比原始 ZIP 更新的内容
- [ ] 只提交打算公开的源码/文档/测试；检查仪器 IP/登录信息/私有数据及厂商 DLL 分发许可
- [ ] 不把运行产生的 logs、outputs、`.pyc`、`__pycache__` 提交
- [ ] 两套 mock 测试通过，并保存终端记录
- [ ] 基础实体 SPI 读取回归通过；如要宣称写入/仪器联动验证，请补对应记录
- [ ] 已知问题列于 Release，未声明为已修复
- [ ] 审查 Pull Request，再合并主分支并打 Tag
