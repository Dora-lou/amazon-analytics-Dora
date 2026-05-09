# Amazon 店铺数据分析系统

这是一个可分享给别人使用的本地数据分析程序。  
- **Windows 电脑**：复制整个 `amazon-analytics` 文件夹，安装 Python 后双击 `启动程序.bat` 即可使用。  
- **macOS 电脑**：同样可以使用，但需要在终端执行几条命令（详见下方“macOS 使用方式”）。

## 怎么打开

### 方式一：本机安装 Python 后运行（开发/调试用，支持 Windows / macOS）

1. 安装 Python 3.10 或更高版本：https://www.python.org/downloads/
2. 安装 Python 时勾选 `Add Python to PATH`。
3. **Windows**：双击 `启动程序.bat`。  
   **macOS**：在终端进入项目目录，执行：

   ```bash
   cd /path/to/amazon-analytics
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install -r requirements.txt
   .venv/bin/streamlit run app.py
   ```
4. 浏览器打开后上传 Amazon 报表。

首次运行会自动创建 `.venv` 环境并安装依赖，需要联网，可能需要几分钟。之后再打开会快很多。

### 方式二：打包成 exe，给没有 Python 的 Windows 电脑用（推荐分享给 Windows 同事）

> 这一步只需要在你自己的电脑上执行一次，用来生成一个带 Python 的 exe。  
> 生成后，把 exe 和 `data` 文件夹一起拷贝到其他电脑，对方就不需要再安装 Python。

1. 在本机（已经有 Python 的这台电脑）双击运行 `打包程序.bat`。
2. 脚本会自动：
   - 创建/更新本地虚拟环境 `.venv`
   - 安装 `requirements.txt` 里的依赖和 `pyinstaller`
   - 调用 `PyInstaller` 把 `run_app.py` 打包成 `店铺数据分析-Dora.exe`
3. 打包完成后，在 `dist` 目录下会生成：
   - `店铺数据分析-Dora.exe`
4. 分享给别人时，至少需要把下面两个拷贝到同一个文件夹：
   - `店铺数据分析-Dora.exe`
   - `data` 目录（里面存放规则模板等数据）
5. 在没有 Python 的电脑上，只需要双击 `店铺数据分析-Dora.exe`，浏览器就会自动打开这个看板。

## 支持的数据文件

- `.xls`
- `.xlsx`
- `.txt`
- `.csv`

可以一次上传多个报表。系统会自动识别日期、产品线、父 ASIN、子 ASIN、品牌、广告类型、花费、销售额、订单数、Session、曝光、点击、ACOS、TACoAS、CTR、CVR、评分、评论数、库存等字段。

如果某个报表没有库存、评分或评论字段，相关模块会自动跳过，不会影响其他分析。

## 主要功能

- 上传 Amazon 报表并自动清洗字段
- 按近 7/14/30/90 天或自定义日期筛选
- 自动生成向前等长对比周期，也支持手动选择对比时间
- 按产品线、品牌筛选
- 查看产品线花费、订单数、销售额、CVR、ACOS、TACoAS、CTR
- 顶部 KPI 卡片展示主值、环比箭头、环比颜色和 hover 绝对变化
- 指标口径：`ACOS = 花费 / 广告销售额`，`TACoAS = 花费 / 总销售额`，`CVR = 订单数总和 / Session-Total 总和`
- 所有核心分析默认以父 ASIN 汇总，父 ASIN 数据由子 ASIN 汇总后重新计算比率
- 默认展示曝光、点击、销售、花费、订单、Session、CTR、CVR、CPC、ACOS、TACoAS，并支持自定义选择列；环比可单独开关显示
- 推荐表现好的父 ASIN / 子 ASIN
- 预警高 ACOS、高 TACoAS、低 CVR、低评分、库存积压、缺货风险
- 父 ASIN 和子 ASIN 双维度广告诊断：高风险、可放量，并输出优化建议
- 分析 SP / SB / SBV / SD / ST 等广告渠道表现、花费占比和销售占比
- 支持识别 `SBV广告费`、`SP广告费`、`SB广告费`、`SD广告费`、`ST广告费` 及对应广告销售额/订单量字段
- 库存只取筛选期最后一天，并自动合并父 ASIN 下所有子 ASIN 的“可售”库存字段，计算预计可售天数和补货风险
- 评分与口碑预警
- 每个模块表格可单独下载，整体也可导出 Excel 分析报告和 PDF 摘要
- 页面展示数据更新时间
- 保存历史数据，用于后续趋势对比

## 文件说明

- `app.py`：主程序源码
- `requirements.txt`：程序依赖
- `启动程序.bat`：Windows 一键启动脚本
- `data/history.csv`：点击“保存为历史数据”后自动生成

## 分享给别人

### 分享给 Windows 同事

推荐先在你自己的电脑上运行一次 `打包程序.bat`，生成 `dist/店铺数据分析-Dora.exe`，再把：

- `店铺数据分析-Dora.exe`
- `data` 文件夹（如有）

一起压缩发送给对方。对方解压后**直接双击 exe 即可使用**，无需安装 Python。

### 分享给 macOS 同事

1. 不建议发 exe（exe 只能在 Windows 上运行）。  
2. 直接把整个 `amazon-analytics` 文件夹压缩发给 Mac 同事。  
3. 让对方在 Mac 上：

   ```bash
   cd /解压后的/amazon-analytics
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install -r requirements.txt
   .venv/bin/streamlit run app.py
   ```

4. 终端显示 `Local URL: http://localhost:8501` 后，在浏览器打开这个地址即可使用。

## 常见问题

### 双击后提示找不到 Python

请安装 Python，并确认安装时勾选了 `Add Python to PATH`。

### 首次打开很慢

首次运行会安装依赖，属于正常情况。之后再次打开会明显变快。

### 上传后某个模块没有显示

说明当前报表没有识别到该模块需要的数据。例如没有评分/评论字段时，评分口碑模块会自动跳过。
