---
name: engineering-microinnovation
description: 将工程现场问题整理为需求、方案比选及结构化设计参数；对 CASE-001 下倒角加固装置，用随包 Python 脚本生成同源三维查看器、模型效果图、DXF、Excel 和成果文档草案，并执行软件校核与人工复核交接。适用于工程微创新孵化和既有案例复现；不替代结构设计或正式审定。
---

# 工程微创新孵化平台

版本 0.1.0。当前真实生成范围：CASE-001 下倒角加固装置，固定总体布局、9 项可调尺寸。新的部位、布局或装置可以先做需求与方案分析，但必须新增并测试生成器后才能声称支持真实生成。

## 核心分工

- AI：理解问题、补齐缺项、比较方案、整理输入 JSON、编写有依据的文字草案。不得直接画工程图、编造构件数量、伪造生成结果或工程批准。
- Python：确定实例、计算数量、生成几何和全部文件、检查并回读成果。数量从实例计算，既有源文件记录数量也不是最终清单权威。
- 工程师：确认荷载、规范适用、材料、连接及受力关键结论；加工制作、正式申报必须经专业复核。

## 先识别执行能力

1. 找到本 Skill 的实际目录，不假设安装路径。读取 `references/platform-trial.md`。
2. 如宿主允许 Python 3.10+ 和文件写入，调用下方 `probe`。无需 pip、网络、服务器、Codex、SketchUp 或 CAD。
3. 如无法执行 Python，进入“思考模式”：完成需求表、方案比选、待运行的 JSON 和缺项说明；明确模型/图纸/Excel 尚未生成。不能只因宿主支持对话或已安装 Skill 就声称脚本可运行。不要引导普通用户安装专业软件来绕过缺失能力。
4. 文件输出成功之后，仍需使用宿主提供的附件/文件下载功能交付。沙箱内部路径不等于用户已经下载。

## 工作流程

### 1. 收集和比选

读取 `references/requirements-form.md` 和 `references/options-rules.md`。分清用户输入、历史事实、待确认设计假设。未知荷载或未给规范原文可以生成清楚标注的评审草案，但不得据此作承载合格或符合规范的结论。

首例复现从 `assets/case001/input.example.json` 复制，按 `schemas/input.schema.json` 填写。读取 `scripts/parameter_schema.json` 理解每项来源与范围。范围是软件试验约束，不是承载安全范围。

### 2. 参数化

保持 `case_id=CASE-001`，完整填写 `parameters_mm`。不得添加 `quantity`、`count` 等 AI 数量字段；未知字段会被拒绝。

用户已确认基准：压板 10 mm、销轴 20 mm、钢管 Φ48×3.5 mm。槽形腹板/翼缘 6 mm、角形厚 5 mm、耳板厚 8 mm、孔销直径差 2 mm 为可调假设。50×100 槽形、50×50 角形是设计外形，不能直接认定为标准采购型号。

`narrative` 是思考文本输入；几何参数与清单由程序填入文档，不在叙述里另行手抄数量和尺寸。未给现场证据、专利权利要求或 QC 数据时保留“待补充”，不虚构效益或检测结果。

### 3. 执行脚本

以下命令在 Skill 目录运行；输入和输出路径可指定在宿主可写空间，输出目录必须是新目录。Windows 也可用宿主提供的 Python 可执行文件代替 `python`。

```text
python scripts/run.py probe --out output/probe-01
python scripts/run.py generate --input assets/case001/input.example.json --out output/case001-run1
python scripts/run.py verify --out output/case001-run1
```

正式处理用户输入时，将示例路径换为本次 JSON 文件。不要为安装执行系统配置修改或启动服务。`generate` 只读输入和随包资料、写入指定的新目录；不覆盖既有成果。错误返回非零退出码和 JSON 信息。

### 4. 校核—修改循环

读取 `manifest.json` 和 `06_checks`。软件校核失败时把具体字段、实测值和差异反馈给 AI；在用户已给约束内修正 JSON，使用新目录重跑。最多自动修正两轮；涉及工程取值、缺失资料或未知错误则保留失败记录并说明缺口，不能反复猜测数值。不要改校核脚本以使错误通过。

生成和校核状态、规范证据状态、人工确认状态必须分别表述。`software_checks_passed_engineering_pending` 表示软件检查通过、工程确认未完成。

### 5. 成果交付

优先给用户下载 `02_model/viewer.html`、`02_model/render.png`、DXF、Excel、成果草案及校核报告；可将整个输出目录压缩交付。HTML 内嵌 three.js 和模型，不需要联网或服务器；宿主若屏蔽 HTML 脚本，下载后用支持 WebGL 的浏览器打开。浏览器可旋转、缩放、剖切及导出当前模型截图，剖切不封口。

读取 `references/output-contract.md` 解释文件含义。DXF 为三视图、截面、节点和编号索引的线框设计草案；未完成 CAD 内核隐藏线、制造公差或正式图审。模型效图由网格栅格渲染，不使用 AI 绘图。

`07_review/confirmation.template.json` 仅供工程师另行填写留档；程序永不自动批准。专业软件导入能力以工程师实际版本/插件为准，不承诺所有 SketchUp 版本原生支持 glTF/OBJ。

## 文档扩展

当前支持 `scheme`（方案）、`method`（工法）、`patent`（专利交底）、`qc`（QC）四种结构化草案模板。AI 提供文本，程序按模板编排 Markdown 和 Word，并附同源参数；并未自动完成合规申报材料。增加类型时同步更新 `templates/document_types.json`、输入 schema 和测试；不用修改几何生成器。

## 平台与重复性验收

按 `references/platform-trial.md` 执行。用户当前首试入口为“工作伙伴里的 evolution”。在此版本交付时，该入口及 aily 均未实际安装验证。文档描述的通用能力不能替代具体租户实测。

分别记录：带脚本包能否安装、Python 能否执行、用户能否下载文件、同一自然语言需求三次输出是否一致。固定参数的本地三次哈希一致，只证明脚本确定性，不证明 AI 三次参数相同。无证据的项目写“未验证”。
