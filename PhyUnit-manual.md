# PhyUnit 宏包手册

> 中学物理单位宏包 —— 版本 0.3.1，日期 2026-10-04

`PhyUnit` 提供了一整套中学物理（以及部分其它学科）常用单位的排版命令，所有命令均以 `\U` 开头，例如 `\Um`、`\Ukg`、`\UN`。所有命令都带有一个可选的“空格参数”，可以方便地控制单位前是否插入空隙。

## 目录

- [1. 简介](#1-简介)
- [2. 安装与加载](#2-安装与加载)
- [3. 使用方法](#3-使用方法)
- [4. 命令分类参考](#4-命令分类参考)
- [5. 完整命令清单](#5-完整命令清单)
- [6. 示例](#6-示例)

## 1. 简介

`PhyUnit` 使用 LaTeX3 的 `expl3` 语法编写，需要 LaTeX2e（2021-11-15 或之后）以及 `expl3` 支持；当存在 `upgreek` 宏包时会加载它以提供直立的 `\upmu`，否则使用内置的回退定义。

物理单位在排版时应当使用直立字体（`\mathrm`），并且在数值与单位之间留出适当的空隙。`PhyUnit` 已经为每一条命令内置了这一处理，用户只需按语义书写即可。

## 2. 安装与加载

把 `PhyUnit.sty` 放到当前目录或 TeX 的宏包搜索路径中，然后在导言区加载：

```latex
\usepackage{PhyUnit}
```

由于 `PhyUnit` 会输出 `Ω`、`μ`、`Å` 等字符的相关字形，建议使用 XeLaTeX 或 LuaLaTeX 编译含有中文的文档；纯英文文档使用 pdfLaTeX 也可以。

## 3. 使用方法

### 3.1 基本用法

所有单位命令都需要在数学模式中使用，例如：

```latex
$v = 3 \Ums$          % 输出 v = 3 m/s
$m = 5 \Ukg$          % 输出 m = 5 kg
$F = 10 \UN$          % 输出 F = 10 N
```

渲染效果：$v = 3 \Ums$，$m = 5 \Ukg$，$F = 10 \UN$。

### 3.2 空格参数

每条命令都接受一个可选参数，用于控制单位前是否留出空隙：

- 不给出参数（默认）：单位前插入一个薄空格 `\,`，适用于“数值 + 单位”的常规写法；
- 给出参数 `a`（表示 *attached*，紧贴）：不插入任何空格，适用于单位之间的相乘，或需要与前面的内容紧贴的情况。

```latex
$5\Um$      % 5 m      （数值与单位间有薄空格）
$5\Um[a]$   % 5m       （紧贴，无空格）
$\Um\Us$    % m s      （两个单位之间默认有空格）
$\Um[a]\Us[a]$ % ms   （单位乘积或词头 + 单位，紧贴）
```

注意：`\Udu`（角度 `°`）和 `\Uspace`（空格本身）的默认值就是 `a`（紧贴），因为它们通常直接跟在数字后面，例如 `30\Udu` 得到 30°。如果要让它们插入空格，需要显式给出一个非 `a` 的参数，例如 `\Udu[]`。

### 3.3 与其它命令配合

`\Uspace` 可以用来手动产生一个与单位相同的薄空格：

```latex
$1.0\Uspace\mathrm{N}$
```

## 4. 命令分类参考

下表中“输出”一列为该命令默认参数下的排版结果。

### 长度

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Um` | m | m （长度） |
| `\Ucm` | cm | cm （长度） |
| `\Udm` | dm | dm （长度） |
| `\Umm` | mm | mm （长度） |
| `\Ukm` | km | km （长度） |
| `\Unm` | nm | nm （长度） |
| `\Upm` | pm | 长度：pm |
| `\Ufm` | fm | 长度：fm |
| `\Uum` | μm | μm （长度，微米） |
| `\UAi` | Å | Å（长度，埃） |
| `\Unmi` | nmi | 长度：海里 n mile（建议用国际符号 nmi） |
| `\Uly` | ly | 天文：光年 ly |
| `\Upc` | pc | 天文：秒差距 pc |
| `\UAU` | AU | AU （天文单位） |
| `\Umn` | m⁻¹ | m^{-1} （长度 m 的倒数） |

### 面积

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Umq` | m² | m^2 （面积） |
| `\Ucmq` | cm² | cm^2 （面积） |
| `\Ummq` | mm² | mm^2 （面积） |
| `\Ukmq` | km² | km^2 （面积） |
| `\Umnq` | m⁻² | m^{-2} （长度 m 的倒数） |

### 体积与容积

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Umc` | m³ | m^3 （体积） |
| `\Ucmc` | cm³ | cm^3 （体积） |
| `\Udmc` | dm³ | dm^3 （体积） |
| `\Ummc` | mm³ | mm^3 （体积） |
| `\UL` | L | L （容积单位，升） |
| `\UmL` | mL | mL （体积） |
| `\Uimp` | imp | imp （体积，容量） |
| `\Umnc` | m⁻³ | m^{-3} （体积倒数） |

### 质量

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Ukg` | kg | kg （质量） |
| `\Ug` | g | g （质量） |
| `\Umg` | mg | mg （质量） |
| `\Uug` | μg | 质量：μg |
| `\Ung` | ng | 质量：ng |
| `\Ut` | t | t 质量单位（吨） |
| `\Uu` | u | u （原子质量单位） |
| `\Ukgs` | kg/s | kg/s |
| `\Ukgm` | kg/m | 质量线密度：kg/m 千克每米 |
| `\UGeVcSq` | GeV/c² | 质量：GeV/c² 吉电子伏特每光速平方 |
| `\UMeVcSq` | MeV/c² | 质量：MeV/c² 兆电子伏特每光速平方 |

### 时间

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Us` | s | s （时间） |
| `\Umin` | min | min （时间） |
| `\Uh` | h | h （时间） |
| `\Ud` | d | 时间： d（天） |
| `\UmsT` | ms | 时间：ms 毫秒 |
| `\Uus` | μs | 时间：μs |
| `\Uns` | ns | 时间：ns |
| `\Usn` | s⁻¹ | s^{-1} （时间倒数） |
| `\Usnq` | s⁻² | s^{-2} （时间负二次方） |
| `\Usq` | s² | s^2 |
| `\Uhn` | h⁻¹ | h^{-1} （时间倒数） |
| `\Ufs` | fs | 时间：fs 飞秒 |
| `\Ups` | ps | 时间：ps 皮秒 |

### 速度

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Ums` | m/s | m/s （速度） |
| `\Ucms` | cm/s | cm/s （速度） |
| `\Ukmh` | km/h | km/h （速度） |
| `\Ukms` | km/s | km/s （速度） |
| `\Umdsn` | m·s⁻¹ | m·s^{-1} （速度） |
| `\Umh` | m/h | m/h （速度） |
| `\Umms` | mm/s | 速度：mm/s 毫米每秒 |
| `\Umqs` | m²/s | 复合：m²/s 平方米每秒（运动黏度） |

### 加速度

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Umsq` | m/s² | m/s^2 （加速度） |
| `\Ucmsq` | cm/s² | cm/s^2 （加速度） |
| `\Ukmsq` | km/s² | km/s^2 （加速度） |

### 力

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UN` | N | N （力） |
| `\UkN` | kN | kN （力） |
| `\Ukgf` | kgf | kgf （千克力） |
| `\Udyn` | dyn | dyn （力单位） |
| `\Ukgmsq` | kg·m/s² | kg·m/s^2 （力的单位，F=ma） |
| `\UNm` | N/m | N/m （弹簧劲度系数） |
| `\UNcm` | N/cm | N/cm （弹簧劲度系数） |
| `\UNkg` | N/kg | N/kg |
| `\UmN` | mN | 力：mN 毫牛 |
| `\UNmm` | N/mm | 劲度系数：N/mm 牛每毫米 |
| `\UNmn` | m/N | 劲度系数倒数：m/N 米每牛（与毫牛 \UmN 区分） |
| `\UNsqmq` | N·s²/m² | 复合：N·s²/m² 牛秒平方每平方米 |

### 力矩、动量与冲量

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UNcdotm` | N·m | N·m （力矩） |
| `\UNs` | N·s | N·s （动量，冲量） |
| `\Ukgms` | kg·m/s | kg·m/s （冲量动量单位，p=mv） |

### 压强

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UPa` | Pa | Pa （压强） |
| `\UkPa` | kPa | kPa （压强） |
| `\UMPa` | MPa | 压强：MPa |
| `\UhPa` | hPa | 压强：hPa 百帕 |
| `\Uatm` | atm | atm （压强单位，标准大气压） |
| `\UmmHg` | mmHg | mmHg （压强单位，毫米汞柱） |
| `\UcmHg` | cmHg | cmHg （压强单位，厘米汞柱） |
| `\UNmq` | N/m² | N/m^2 （压强） |
| `\Ukgcmq` | kg/cm² | 压强：kg/cm² 千克每平方厘米 |

### 能量与功

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UJ` | J | J （能量，功） |
| `\UkJ` | kJ | kJ （能量，热量） |
| `\UMJ` | MJ | 能量：MJ |
| `\UmJ` | mJ | 能量：mJ |
| `\UuJ` | μJ | 能量：μJ |
| `\UeV` | eV | eV （能量，电子伏特） |
| `\UMeV` | MeV | MeV （能量，兆电子伏特） |
| `\UGeV` | GeV | 能量：GeV 吉电子伏特 |
| `\UkeV` | keV | 能量：keV 千电子伏特 |
| `\Uerg` | erg | erg （能量单位） |
| `\Ucal` | cal | cal （卡路里，简称卡，符号 cal，热量的旧单位） |
| `\Ukcal` | kcal | 热量：kcal |
| `\Ukgmqsq` | kg·m²·s⁻² | kg·m²·s⁻² （能量的单位，J） |
| `\UJcal` | J/cal | 热功当量：J/cal 焦耳每卡 |
| `\UJcdots` | J·s | J·s（普朗克常数 h 单位） |
| `\UJg` | J/g | 比热/潜热：J/g 焦耳每克 |
| `\UJgdC` | J/(g·°C) | 比热：J/(g·℃) 焦耳每克摄氏度 |
| `\UJm` | J/m | 复合：J/m 焦耳每米 |
| `\UJmc` | J/m³ | J/m^3 （能量密度） |
| `\UJsmq` | J/(s·m²) | J/(s·m^2) （能流密度、太阳辐射功率密度） |
| `\UkJg` | kJ/g | kJ/g （熔解热、汽化热） |
| `\UeVm` | eV·m | eV·m （hc 的单位） |
| `\Ukgmqs` | kg·m²/s | 复合：kg·m²/s 千克二次方米每秒（普朗克常量单位） |
| `\UkWh` | kW·h | kW·h （电能，度） |
| `\UWh` | W·h | 电能：W·h |
| `\UAh` | A·h | 电能：A·h |

### 功率

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UW` | W | W （功率） |
| `\UkW` | kW | kW （功率） |
| `\UMW` | MW | 功率：MW |
| `\UmW` | mW | 功率：mW |
| `\UHP` | HP | HP （功率单位：马力，horsepower） |
| `\UJs` | J/s | J/s （功率） |
| `\UWmq` | W/m² | W/m^2 |
| `\Ukgmqsc` | kg·m²/s³ | 功率：kg·m²/s³ 千克二次方米每秒三次方 |

### 电流

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UA` | A | A （电流） |
| `\UAm` | A·m | A·m |
| `\UmA` | mA | mA （电流，毫安） |
| `\UuA` | μA | μA （电流，微安） |
| `\UmuA` | μA | μA （电流，微安） |
| `\UkA` | kA | 电流：kA |
| `\UnA` | nA | 电流：nA |
| `\UpA` | pA | 电流：pA |
| `\UAs` | A/s | A/s （电流强度变化率） |
| `\UAmq` | A/m² | A/m^2 （电流密度） |

### 电压

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UV` | V | V （电压） |
| `\UmV` | mV | mV （电压） |
| `\UkV` | kV | kV （电压） |
| `\UMV` | MV | 电压：MV |
| `\UuV` | μV | 电压：μV |
| `\UJC` | J/C | J/C （同电压） |
| `\UWbs` | Wb/s | Wb/s （同电压） |
| `\UCF` | C/F | 电压等效单位：C/F 库仑每法拉 |
| `\UTmqs` | T·m²/s | 电压等效单位：T·m²/s 特斯拉二次方米每秒 |
| `\UWA` | W/A | 电压等效单位：W/A 瓦每安培 |

### 电阻、电阻率与电导

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UO` | Ω | Ω （电阻） |
| `\UkO` | kΩ | kΩ （电阻） |
| `\UMO` | MΩ | MΩ （电阻） |
| `\UmO` | mΩ | 电阻：mΩ |
| `\UGO` | GΩ | 电阻：GΩ |
| `\UOm` | Ω·m | Ω·m （电阻率） |
| `\UVA` | V/A | V/A （同电阻） |
| `\UsF` | s/F | s/F （同电阻） |
| `\UHs` | H/s | H/s （同电阻） |
| `\UsVC` | s·V/C | s·V/C （同电阻） |
| `\UOs` | Ω·s | Ω·s （同自感系数） |
| `\UCV` | C/V | C/V （同电容） |
| `\UOmdiv` | Ω/m | Ω/m （导线单位长度电阻） |
| `\UOpm` | Ω/m | 电阻线密度：Ω/m 欧姆每米（同 \UOmdiv） |
| `\UOmn` | Ω⁻¹·m⁻¹ | Ω^{-1}·m^{-1} （电导率） |
| `\USm` | S/m | S/m （电导率，同 \UOmn） |

### 电场强度

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UNC` | N/C | N/C （电场强度） |
| `\UVm` | V/m | V/m （同电场强度） |
| `\UVcm` | V/cm | V/cm （同电场强度） |
| `\UkVm` | kV/m | 电场强度：kV/m, |
| `\UkVcm` | kV/cm | 电场强度：kV/cm |

### 电容

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UF` | F | F （电容） |
| `\UmF` | mF | 电容：mF |
| `\UuF` | μF | μF （电容） |
| `\UmuF` | μF | μF （电容） |
| `\UnF` | nF | nF （电容） |
| `\UpF` | pF | pF （电容） |
| `\UFm` | F/m | F/m （介电常数 ε 的单位） |
| `\UMF` | MF | 电容：MF 兆法拉 |

### 电感与自感

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UH` | H | H （自感系数） |
| `\UmH` | mH | mH （自感系数） |
| `\UuH` | μH | μH （自感系数） |
| `\UmuH` | μH | μH （自感系数） |
| `\UnH` | nH | 电感：nH |
| `\UVsA` | V·s/A | V·s/A （同自感系数） |

### 电荷量

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UC` | C | C （电荷量） |
| `\UmC` | mC | 电荷：mC |
| `\UuC` | μC | 电荷：μC |
| `\UnC` | nC | 电荷： nC |
| `\Ue` | e | e （元电荷） |
| `\UAcdots` | A·s | A·s （同电荷单位库仑） |

### 磁学

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UT` | T | T （磁感应强度，特斯拉） |
| `\UmT` | mT | 磁场：mT, |
| `\UuT` | μT | 磁场：μT |
| `\UGs` | Gs | 磁场： Gs（高斯） |
| `\UMx` | Mx | 磁场： Mx（麦克斯韦） |
| `\UWb` | Wb | Wb （磁通量） |
| `\UWbmq` | Wb/m² | Wb/m^2 （磁通密度，同磁感应强度） |
| `\UTmq` | T·m² | T·m^2 （同磁通量） |
| `\UTm` | T/m | T/m 磁场随距离变化系数 |
| `\UCTms` | C·T·m/s | 复合单位：C·T·m/s 库仑特斯拉米每秒 |
| `\UTA` | T/A | 磁场系数：T/A 特斯拉每安培 |
| `\UTAm` | T·A·m | 复合单位：T·A·m 特斯拉安培米 |
| `\UTmA` | T·m/A | 磁场系数：T·m/A 特斯拉米每安培 |
| `\UTs` | T/s | 磁场变化率：T/s 特斯拉每秒 |
| `\UuWb` | μWb | 磁通量：μWb 微韦伯 |
| `\UmuWb` | μWb | 磁通量：μWb 微韦伯 |

### 频率

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UHz` | Hz | Hz （频率） |
| `\UkHz` | kHz | kHz （频率） |
| `\UMHz` | MHz | MHz （频率） |
| `\UGHz` | GHz | 频率：GHz |
| `\UTHZ` | THz | 频率：THz 太赫兹 |

### 温度

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UK` | K | K （热力学温度） |
| `\UdC` | °C | ℃ (温度单位，摄氏度，degree Celsius，简写为dC) |
| `\UduC` | °C | ℃ (温度单位，摄氏度，简写为duC) |
| `\UdF` | °F | 温度：℉ |
| `\UduF` | °F | 温度：℉ |
| `\UdCn` | °C⁻¹ | ℃^{-1} （电阻率温度系数的单位） |
| `\UKn` | K⁻¹ | K^{-1} （线膨胀系数、温度系数的单位） |

### 角度与角速度

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Udu` | ° | ° （角度单位） |
| `\Uprime` | ′ | 角度：角分 ′ |
| `\Upprime` | ″ | 角度：角秒 ″ |
| `\Urad` | rad | rad （弧度） |
| `\Urads` | rad/s | rad/s （角速度） |
| `\Uradmin` | rad/min | rad/min （角速度） |
| `\Usr` | sr | 角度：球面度 sr |

### 物质的量

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Umol` | mol | mol （物质的量） |
| `\Ummol` | mmol | 物质的量：mmol |
| `\Uumol` | μmol | 物质的量： μmol |
| `\Umoln` | mol⁻¹ | mol^{-1} （物质的量倒数） |
| `\Umolnq` | mol⁻² | mol^{-2} （物质的量倒数） |
| `\Umolnc` | mol⁻³ | mol^{-3}（物质的量倒数） |

### 摩尔与热学量

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Ukgmol` | kg/mol | kg/mol （摩尔质量单位，化学当量） |
| `\Ugmol` | g/mol | g/mol 化学/热学 |
| `\Umcmol` | m³/mol | m^3/mol （摩尔体积） |
| `\ULmol` | L/mol | L/mol （摩尔体积，升每摩尔） |
| `\UJmolK` | J/(mol·K) | J/(mol·K) （摩尔气体恒量 R 单位） |
| `\UJkg` | J/kg | J/kg （熔解热、汽化热） |
| `\UkJkg` | kJ/kg | kJ/kg （熔解热、汽化热） |
| `\UJkgK` | J/(kg·K) | 比热 J/(kg·K) |
| `\UJkgdC` | J/(kg·°C) | 比热 J/(kg·℃) |
| `\UCmol` | C/mol | C/mol （法拉第恒量 F） |
| `\UJmoldC` | J/(mol·°C) | J/(mol·℃) 化学/热学 |
| `\UatmLmolK` | atm·L/(mol·K) | atm·L/(mol·K) （理想气体状态方程 pV=nRT 中 R 的单位） |
| `\UJK` | J/K | J/K （热容量、玻尔兹曼常量的单位） |
| `\UJKmol` | J·K⁻¹·mol⁻¹ | 定压摩尔热容：J·K⁻¹·mol⁻¹ 焦耳每开尔文摩尔 |
| `\UmK` | m·K | m·K （维恩位移定律常量 b 的单位） |
| `\UWmqKq` | W/(m²·K⁴) | W/(m^2·K^4) （斯特藩-玻尔兹曼常量 σ 的单位） |
| `\Ukgmqskmol` | kg·m²·s⁻²·K⁻¹·mol⁻¹ | 复合：kg·m²·s⁻²·K⁻¹·mol⁻¹（摩尔气体常量 R 的基本单位） |

### 密度与浓度

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Ukgmc` | kg/m³ | kg/m^3 （密度） |
| `\Ugcmc` | g/cm³ | 密度：g/cm^3 |
| `\UmolL` | mol/L | 物质的量浓度：mol/L |
| `\UgL` | g/L | g/L （密度） |

### 电磁学常量单位

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UNmqCq` | N·m²/C² | N·m^2/C^2 （静电力常量 k） |
| `\UNmqkgq` | N·m²/kg² | N·m^2/kg^2 (万有引力常量 G 单位) |
| `\UNAq` | N/A² | N/A^2 （直导线电流产生磁场的比例系数 B=kI/r） |
| `\UCkg` | C/kg | C/kg （电荷与质量之比，荷质比） |
| `\UkgC` | kg/C | kg/C （电化当量） |
| `\UCqNmq` | C²/(N·m²) | 复合单位：C²/(N·m²) 库仑平方每牛二次方米（真空电容率 ε₀ 单位） |
| `\UkgmcmsqAq` | kg·m³·s⁻⁴·A⁻² | 复合：kg·m³·s⁻⁴·A⁻² 静电力常量 k 的基本单位 |

### 声、光与放射性

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UdB` | dB | dB （声音强弱） |
| `\Ucd` | cd | cd 发光强度 |
| `\Ulx` | lx | 光照：lx |
| `\Ulm` | lm | 光照：lm |
| `\UBq` | Bq | 放射性：Bq |
| `\UGy` | Gy | 放射性：Gy |
| `\USv` | Sv | 放射性：Sv |

### 流量

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\ULs` | L/s | 流量：L/s, |
| `\ULmin` | L/min | 流量：L/min |
| `\Umch` | m³/h | 流量： m^3/h |
| `\Umcs` | m³/s | m^3/s （抽水速度） |
| `\Ugs` | g/s | 质量流量：g/s 克每秒 |

### 转速

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\Urmin` | r/min | r/min （转速） |
| `\Urs` | r/s | r/s （转速） |

### 其它

| 命令 | 输出 | 说明 |
| :--- | :--- | :--- |
| `\UmAh` | mA·h | mA·h （电池容量） |
| `\UcalgdC` | cal/(g·°C) | cal/(g·℃) 化学/热学 |
| `\UkcalKgdC` | kcal/(kg·°C) | kcal/(kg·℃) 化学/热学 |
| `\Uspace` | （空格） | 物理单位的空格 |
| `\UmqsmV` | m²/(s·V) | m^2/(s·V) （离子迁移率） |

## 5. 完整命令清单

按字母顺序排列的全部命令：

`\UA`, `\UAU`, `\UAcdots`, `\UAh`, `\UAi`, `\UAm`, `\UAmq`, `\UAs`, `\UBq`, `\UC`, `\UCF`, `\UCTms`, `\UCV`, `\UCkg`, `\UCmol`, `\UCqNmq`, `\UF`, `\UFm`, `\UGHz`, `\UGO`, `\UGeV`, `\UGeVcSq`, `\UGs`, `\UGy`, `\UH`, `\UHP`, `\UHs`, `\UHz`, `\UJ`, `\UJC`, `\UJK`, `\UJKmol`, `\UJcal`, `\UJcdots`, `\UJg`, `\UJgdC`, `\UJkg`, `\UJkgK`, `\UJkgdC`, `\UJm`, `\UJmc`, `\UJmolK`, `\UJmoldC`, `\UJs`, `\UJsmq`, `\UK`, `\UKn`, `\UL`, `\ULmin`, `\ULmol`, `\ULs`, `\UMF`, `\UMHz`, `\UMJ`, `\UMO`, `\UMPa`, `\UMV`, `\UMW`, `\UMeV`, `\UMeVcSq`, `\UMx`, `\UN`, `\UNAq`, `\UNC`, `\UNcdotm`, `\UNcm`, `\UNkg`, `\UNm`, `\UNmm`, `\UNmn`, `\UNmq`, `\UNmqCq`, `\UNmqkgq`, `\UNs`, `\UNsqmq`, `\UO`, `\UOm`, `\UOmdiv`, `\UOmn`, `\UOpm`, `\UOs`, `\UPa`, `\USm`, `\USv`, `\UT`, `\UTA`, `\UTAm`, `\UTHZ`, `\UTm`, `\UTmA`, `\UTmq`, `\UTmqs`, `\UTs`, `\UV`, `\UVA`, `\UVcm`, `\UVm`, `\UVsA`, `\UW`, `\UWA`, `\UWb`, `\UWbmq`, `\UWbs`, `\UWh`, `\UWmq`, `\UWmqKq`, `\Uatm`, `\UatmLmolK`, `\Ucal`, `\UcalgdC`, `\Ucd`, `\Ucm`, `\UcmHg`, `\Ucmc`, `\Ucmq`, `\Ucms`, `\Ucmsq`, `\Ud`, `\UdB`, `\UdC`, `\UdCn`, `\UdF`, `\Udm`, `\Udmc`, `\Udu`, `\UduC`, `\UduF`, `\Udyn`, `\Ue`, `\UeV`, `\UeVm`, `\Uerg`, `\Ufm`, `\Ufs`, `\Ug`, `\UgL`, `\Ugcmc`, `\Ugmol`, `\Ugs`, `\Uh`, `\UhPa`, `\Uhn`, `\Uimp`, `\UkA`, `\UkHz`, `\UkJ`, `\UkJg`, `\UkJkg`, `\UkN`, `\UkO`, `\UkPa`, `\UkV`, `\UkVcm`, `\UkVm`, `\UkW`, `\UkWh`, `\Ukcal`, `\UkcalKgdC`, `\UkeV`, `\Ukg`, `\UkgC`, `\Ukgcmq`, `\Ukgf`, `\Ukgm`, `\Ukgmc`, `\UkgmcmsqAq`, `\Ukgmol`, `\Ukgmqs`, `\Ukgmqsc`, `\Ukgmqskmol`, `\Ukgmqsq`, `\Ukgms`, `\Ukgmsq`, `\Ukgs`, `\Ukm`, `\Ukmh`, `\Ukmq`, `\Ukms`, `\Ukmsq`, `\Ulm`, `\Ulx`, `\Uly`, `\Um`, `\UmA`, `\UmAh`, `\UmC`, `\UmF`, `\UmH`, `\UmJ`, `\UmK`, `\UmL`, `\UmN`, `\UmO`, `\UmT`, `\UmV`, `\UmW`, `\Umc`, `\Umch`, `\Umcmol`, `\Umcs`, `\Umdsn`, `\Umg`, `\Umh`, `\Umin`, `\Umm`, `\UmmHg`, `\Ummc`, `\Ummol`, `\Ummq`, `\Umms`, `\Umn`, `\Umnc`, `\Umnq`, `\Umol`, `\UmolL`, `\Umoln`, `\Umolnc`, `\Umolnq`, `\Umq`, `\Umqs`, `\UmqsmV`, `\Ums`, `\UmsT`, `\Umsq`, `\UmuA`, `\UmuF`, `\UmuH`, `\UmuWb`, `\UnA`, `\UnC`, `\UnF`, `\UnH`, `\Ung`, `\Unm`, `\Unmi`, `\Uns`, `\UpA`, `\UpF`, `\Upc`, `\Upm`, `\Upprime`, `\Uprime`, `\Ups`, `\Urad`, `\Uradmin`, `\Urads`, `\Urmin`, `\Urs`, `\Us`, `\UsF`, `\UsVC`, `\Usn`, `\Usnq`, `\Uspace`, `\Usq`, `\Usr`, `\Ut`, `\Uu`, `\UuA`, `\UuC`, `\UuF`, `\UuH`, `\UuJ`, `\UuT`, `\UuV`, `\UuWb`, `\Uug`, `\Uum`, `\Uumol`, `\Uus`

## 6. 示例

```latex
\documentclass{article}
\usepackage{PhyUnit}
\begin{document}

$c = 3.0\times10^{8}\Ums$\\
$G = 6.67\times10^{-11}\UNmqkgq$\\
$R = 8.31\UJmolK$\\
$e = 1.6\times10^{-19}\UC$\\
$1\UeV = 1.6\times10^{-19}\UJ$\\
$\eta = 0.9$，$P = 100\UkW$\\

\end{document}
```

渲染效果：$c = 3.0\times10^{8}\Ums$；$G = 6.67\times10^{-11}\UNmqkgq$；$R = 8.31\UJmolK$；$e = 1.6\times10^{-19}\UC$。

