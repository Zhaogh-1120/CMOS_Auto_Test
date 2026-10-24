# CMOS_Auto_Test 并联谐振 SAW 版本

该工程在原 `CMOS_Auto_Test-0.2.0` 上只迁移寄存器映射和针对 IBIAS/SWCAP/IND_CAP 的三套测试模板。

**从 `full_flow_test/` 开始运行：**

```bat
python -m scripts.fullflow.parallel_spi_readonly_check
python -m scripts.fullflow.parallel_spi_readonly_check --read
python -m scripts.fullflow.e5052b_capture_once
python -m scripts.fullflow.case_saw_pn_sweep_1param --plan
python -m scripts.fullflow.case_saw_pn_sweep_1param --check-point
```

最重要：`--read` 仅 SPI 读取，不改寄存器；`e5052b_capture_once` 只读仪器、不访问 SPI；`--check-point` 会有寄存器写入，测试后尝试恢复。

新芯片寄存器：`REG05–REG14`；详细字段定义、限制与离线测试结果请参阅 `full_flow_test/docs/register_map_parallel/PARALLEL_MIGRATION_GUIDE.md`。

**注意：保留的旧串联谐振历史 Case 中仍有 REG20–REG22 等旧字段，不要拿这些历史脚本操作并联谐振芯片。**
