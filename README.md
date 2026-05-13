# Gomoku

38 路五子棋命令行 AI，使用 C++17 编写。项目提供两个裁判版程序和两个可视化程序：

想了解 AI 搜索、评估函数、禁手判断和随机版原理，请看 [AI_TECHNICAL_GUIDE.md](AI_TECHNICAL_GUIDE.md)。

- `black.exe`：黑方 AI，启动后立即输出第一手。
- `white.exe`：白方 AI，启动后等待输入黑方第一手，再输出自己的落子。
- `black_show.exe`：黑方 AI，额外在控制台显示棋盘。
- `white_show.exe`：白方 AI，额外在控制台显示棋盘。
- `random_ai/`：随机版 exe 文件夹，同一局面会在近似同分好棋中随机选择。
- `gomoku_referee.py`：Python 图形化裁判，可选择两个 exe 自动对打，也支持用户手动落子。

裁判版用于自动评测或程序交互。标准输出严格只打印坐标，不打印中文、提示语、棋盘或胜负信息。

可视化版用于人工观察。它仍然把坐标写到标准输出，同时把棋盘写到标准错误流；在普通 Windows 黑色控制台中，两者都会显示出来。

## 输入输出协议

坐标范围是 `1..38`，格式固定为一行两个整数：

```text
row col
```

内部数组使用 0-based 坐标，外部输入输出使用 1-based 坐标。

### black.exe

黑方先手，所以程序启动后会立刻输出一个坐标：

```text
19 19
```

之后每输入一行白方坐标，程序输出一行黑方坐标：

```text
12 12
18 19
```

### white.exe

白方后手，启动后不会立即输出。输入黑方一步后，程序输出白方一步：

```text
19 19
20 18
```

之后同样是“读入对手一步，输出自己一步”的循环。读到 EOF 后程序退出。

### 可视化版本

`black_show.exe` 和 `white_show.exe` 的输入方式与普通版本相同。不同点是每次 AI 落子后都会显示完整棋盘：

- `X` 表示黑棋。
- `O` 表示白棋。
- `.` 表示空位。
- 顶部和左侧显示 `1..38` 坐标。

示例：

```powershell
.\black_show.exe
```

黑方会先输出坐标并显示棋盘。之后继续输入白方坐标即可。

## Python 图形化裁判

`gomoku_referee.py` 是一个单文件 Tkinter 裁判程序，不需要安装第三方库。它会独立维护棋盘和规则，不依赖参赛 exe 自己判断胜负或禁手。

启动方式：

```powershell
python gomoku_referee.py
```

主要功能：

- 支持 `黑 exe vs 白 exe`、`用户黑 vs exe 白`、`exe 黑 vs 用户白`、`用户 vs 用户` 四种模式。
- 可以在界面中分别选择黑方和白方 exe。
- 用户落子时直接点击棋盘交点。
- 自动判断越界、重复落子、黑方三三禁手、四四禁手、长连禁手、胜负和平局。
- 黑方如果本手形成恰好五连，即使同时出现禁手形状，也按黑方胜利处理。
- exe 输出支持模糊解析：stdout 中可以带中文、提示语等内容，裁判会抓取第一组当前可用的合法坐标。
- 黑方 exe 第一手 5 秒未输出时，裁判会在中心 9 格随机落一手，不判负。
- 普通回合 10 秒超时，当前一方直接判负。
- 界面右侧显示日志和累计比分；每盘结束后可用进度条复盘任意手数。

注意：

- 裁判只从 exe 的标准输出 `stdout` 解析坐标。
- 标准错误 `stderr` 会进入日志，但不会参与落子解析。
- 给 exe 的输入仍然是 `row col`，坐标范围仍为 `1..38`。
- 累计比分只保存在本次程序运行期间，关闭程序后不会自动保存。

## 编译

本项目使用同一个 `main.cpp` 通过编译宏生成不同 exe。

```powershell
g++ -O2 -std=c++17 -DBLACK_AI main.cpp -o black.exe
g++ -O2 -std=c++17 -DWHITE_AI main.cpp -o white.exe
g++ -O2 -std=c++17 -DBLACK_AI -DSHOW_BOARD main.cpp -o black_show.exe
g++ -O2 -std=c++17 -DWHITE_AI -DSHOW_BOARD main.cpp -o white_show.exe
g++ -O2 -std=c++17 -DBLACK_AI -DSUPER_AI main.cpp -o black_super.exe
g++ -O2 -std=c++17 -DWHITE_AI -DSUPER_AI main.cpp -o white_super.exe
g++ -O2 -std=c++17 -DBLACK_AI -DFAST_AI main.cpp -o black_fast.exe
g++ -O2 -std=c++17 -DWHITE_AI -DFAST_AI main.cpp -o white_fast.exe
g++ -O2 -std=c++17 -DBLACK_AI -DULTRAFAST_AI main.cpp -o black_ultrafast.exe
g++ -O2 -std=c++17 -DWHITE_AI -DULTRAFAST_AI main.cpp -o white_ultrafast.exe
```

随机版使用同一份源码额外加 `-DRANDOM_AI`，建议统一放到 `random_ai/` 文件夹：

```powershell
mkdir random_ai
g++ -O2 -std=c++17 -DBLACK_AI -DRANDOM_AI main.cpp -o random_ai/black_random.exe
g++ -O2 -std=c++17 -DWHITE_AI -DRANDOM_AI main.cpp -o random_ai/white_random.exe
g++ -O2 -std=c++17 -DBLACK_AI -DSHOW_BOARD -DRANDOM_AI main.cpp -o random_ai/black_show_random.exe
g++ -O2 -std=c++17 -DWHITE_AI -DSHOW_BOARD -DRANDOM_AI main.cpp -o random_ai/white_show_random.exe
g++ -O2 -std=c++17 -DBLACK_AI -DSUPER_AI -DRANDOM_AI main.cpp -o random_ai/black_super_random.exe
g++ -O2 -std=c++17 -DWHITE_AI -DSUPER_AI -DRANDOM_AI main.cpp -o random_ai/white_super_random.exe
g++ -O2 -std=c++17 -DBLACK_AI -DFAST_AI -DRANDOM_AI main.cpp -o random_ai/black_fast_random.exe
g++ -O2 -std=c++17 -DWHITE_AI -DFAST_AI -DRANDOM_AI main.cpp -o random_ai/white_fast_random.exe
g++ -O2 -std=c++17 -DBLACK_AI -DULTRAFAST_AI -DRANDOM_AI main.cpp -o random_ai/black_ultrafast_random.exe
g++ -O2 -std=c++17 -DWHITE_AI -DULTRAFAST_AI -DRANDOM_AI main.cpp -o random_ai/white_ultrafast_random.exe
```

内部规则测试：

```powershell
g++ -O2 -std=c++17 -DSELF_TEST main.cpp -o self_test.exe
.\self_test.exe
```

`SELF_TEST` 成功时没有输出，返回码为 0。

## 规则设计

棋盘大小为 `38x38`，双方交替落子。黑方带禁手，白方无禁手。

黑方主动落子时检查：

- 三三禁手
- 四四禁手
- 长连禁手

特殊规则：

- 黑方如果本手形成“恰好五连”，即使同时出现禁手形状，也按黑方胜利处理。
- 黑方被动形成禁手不判犯规。本程序只在黑方主动尝试落子时调用禁手判断。
- 黑方胜利按“恰好五连”判断；白方胜利按“五连或更长”判断。

## AI 算法原理

### 候选点生成

38 路棋盘共有 1444 个点，直接全盘搜索会非常慢。程序只生成已有棋子附近的空点：

- 开局前几手使用较大邻域，避免漏掉宽松布局。
- 中后盘使用较小邻域，把搜索集中在战斗区域。
- 候选点会按局部形状评分排序，并截断到固定数量。

这样可以显著减少搜索分支，同时保留大部分有意义的攻防点。

### 局部形状评分

每个候选点会同时估计：

- 己方落在这里是否能成五、成四、成三。
- 对手落在这里是否能成五、成四、成三。
- 是否接近棋盘中心。

这个分数主要用于排序，让 alpha-beta 更早看到强手，从而产生更多剪枝。

### 局面评估

静态评估函数扫描所有连续 5 格窗口：

- 己方五连给极高正分。
- 对手五连给极高负分。
- 活四、三、二等形状按威胁大小加减分。
- 同一个 5 格窗口中同时有黑白棋时，该窗口价值为 0。

评估函数从当前 AI 的视角返回分数。

### 搜索

程序使用迭代加深 alpha-beta 搜索：

- 当前默认时间上限约 `1.5` 秒。
- 最大搜索深度为 `4` 层。
- 根节点最多保留 `30` 个候选点。
- 深层节点候选数为 `depth >= 3 ? 14 : 20`。

搜索前会先做两个战术快捷判断：

1. 如果己方有一步成五，立即下。
2. 如果对手有一步成五，立即挡。

这能避免在显然的必胜必防局面上浪费搜索时间。

### 置换表

程序使用 Zobrist 哈希记录局面，并用 `unordered_map` 保存搜索结果。置换表条目包括：

- 搜索深度
- 估值
- exact / lower bound / upper bound 标记

同一个局面如果通过不同落子顺序到达，可以复用已有搜索结果。

### 随机版

默认 exe 是确定性的：固定输入通常会得到固定输出，便于调试和复现。使用 `-DRANDOM_AI` 编译的随机版会做两件事：

- 第一手从中心附近的合法点中随机选择。
- 搜索完成后，如果多步棋的评分非常接近，就从这些近似同分好棋中随机选一步。

随机版仍会优先处理必胜和必防，不会因为随机而放弃一步成五或挡五。

默认情况下，随机版每次启动会使用不同种子。如果需要复现同一盘，可以设置环境变量：

```powershell
$env:GOMOKU_SEED=12345
.\random_ai\black_random.exe
```

同一个 `GOMOKU_SEED` 加同样输入，会得到同样输出。

## 参数档位和文件名

当前 `black.exe` / `white.exe` 是中等档：

```cpp
milliseconds(1500)
depth <= 4
rootMoves 30
depth >= 3 ? 14 : 20
```

额外提供 3 个纯坐标档位：

| 档位 | 黑方 | 白方 | 时间 | 深度 | 根候选 | 深层/浅层候选 |
| --- | --- | --- | --- | --- | --- | --- |
| 超级 | `black_super.exe` | `white_super.exe` | `2800ms` | `5` | `40` | `18 / 26` |
| 中等 | `black.exe` | `white.exe` | `1500ms` | `4` | `30` | `14 / 20` |
| 快速 | `black_fast.exe` | `white_fast.exe` | `900ms` | `4` | `24` | `10 / 16` |
| 超快速 | `black_ultrafast.exe` | `white_ultrafast.exe` | `350ms` | `3` | `18` | `8 / 12` |

可视化版 `black_show.exe` / `white_show.exe` 使用中等档参数，并额外显示棋盘。

`random_ai/` 文件夹中提供同样档位的随机版：

| 档位 | 黑方随机版 | 白方随机版 |
| --- | --- | --- |
| 中等 | `black_random.exe` | `white_random.exe` |
| 中等可视化 | `black_show_random.exe` | `white_show_random.exe` |
| 超级 | `black_super_random.exe` | `white_super_random.exe` |
| 快速 | `black_fast_random.exe` | `white_fast_random.exe` |
| 超快速 | `black_ultrafast_random.exe` | `white_ultrafast_random.exe` |

如果想手动改得更快，可以把默认参数改成：

```cpp
milliseconds(900)
depth <= 4
rootMoves 24
depth >= 3 ? 10 : 16
```

如果想更强，可以把参数改成：

```cpp
milliseconds(2800)
depth <= 5
rootMoves 40
depth >= 3 ? 18 : 26
```

改完后重新编译两个 exe 即可。

## 文件说明

- `main.cpp`：完整 AI、规则、搜索和交互入口。
- `black.exe`：黑方可执行程序。
- `white.exe`：白方可执行程序。
- `black_show.exe`：黑方可视化程序。
- `white_show.exe`：白方可视化程序。
- `gomoku_referee.py`：Python 图形化裁判，支持 exe 对打、用户对打、日志、复盘和累计比分。
- `black_super.exe` / `white_super.exe`：超级档，棋力更强但更慢。
- `black_fast.exe` / `white_fast.exe`：快速档。
- `black_ultrafast.exe` / `white_ultrafast.exe`：超快速档。
- `random_ai/`：随机版 exe 文件夹，包含中等、显示、超级、快速、超快速随机版。

## 验证建议

基础协议测试：

```powershell
@('12 12') | .\black.exe
@('19 19') | .\white.exe
@('12 12','14 14','15 15') | .\black.exe
```

输出应该始终只包含坐标行，例如：

```text
19 19
18 19
```

可视化版本测试：

```powershell
@('12 12') | .\black_show.exe
@('19 19') | .\white_show.exe
```

坐标会继续输出，棋盘会显示在控制台中。

随机版复现测试：

```powershell
$env:GOMOKU_SEED=12345
@('12 12') | .\random_ai\black_random.exe
@('12 12') | .\random_ai\black_random.exe
Remove-Item Env:\GOMOKU_SEED
```

设置相同种子时，同样输入应输出一致；不设置种子时，多次运行有概率输出不同。

禁手测试通过 `SELF_TEST` 覆盖：

- 黑方长连禁手。
- 黑方三三禁手。
- 黑方四四禁手。
- 黑方恰好五连优先于禁手。

图形化裁判测试：

```powershell
python gomoku_referee.py
```

可在界面中选择 `black.exe` 和 `white.exe` 进行自动对打，也可以切换到用户模式后点击棋盘手动落子。
