# 输出与分层契约

| 阶段目录 | 文件 | 权威来源 |
|---|---|---|
| 00_input | requirements.json | 用户/现场资料 |
| 01_parameters | input.canonical.json、parameter_provenance.json；components.derived.json、connections.derived.json | AI 整理的受限输入；脚本展开完整构件/截面/尺寸/连接/实例数量表 |
| 02_model | scene.json、viewer.html、model.gltf、model.obj、render.png | Python 确定性几何 |
| 03_drawings | D01 总装三视图、D02 真实截面、D03 铰接节点、D04 编号索引 | 同源几何投影，DXF |
| 04_bom | quantities.json、components.xlsx | 构件实例及同规格分组计数 |
| 05_documents | scheme/method/patent/qc 的 .md、.docx | 模板 + AI 文本 + 脚本参数 |
| 06_checks | geometry、readback、standards 报告 | 程序校核与缺项 |
| 07_review | confirmation.template.json、README | 工程师复核，默认 pending |
| 根目录 | manifest.json | 输入哈希、脚本哈希、成果哈希 |

统一规则：输入 schema 版本固定；CASE-001 + 输入/脚本内容摘要生成编号；目录阶段统一；同参数、同输入文本、同版本脚本在本地测试环境下得到一致文件。不同 AI 生成的叙述或参数会改变输入哈希，必须如实记录差异。跨 Python/操作系统的逐字节一致性尚未单独验证。

坐标：scene/OBJ 为 mm、Z 向上；glTF 为 m、Y 向上（X,Y,Z→X,Z,-Y）。OBJ 单独不含颜色；glTF 内嵌缓冲区并含外观材质。名称与外观材质不是材料牌号。

数量：234 是首例基准软件生成的几何实例数，含螺母、垫片、简化件和既有边界；不是采购数量。脚本每次重新计算，不能作为输入写死。

工程限制：传振节点细化尚未完成；螺纹简化；焊缝、材质与制造公差未批准；无受力/疲劳/稳定验算；标准原文与现行性未验证；未生成可直接申报的正式文件。

技术依赖：Python 3.10+ 标准库；浏览器需 JavaScript/WebGL。three.js r160 固定内嵌，MIT 许可见 assets/vendor/THREE-LICENSE.txt，哈希见 lock.json。生成阶段不下载资源、不联网。旧版固定依赖是可复现基线，并非声称它是最新版本。
