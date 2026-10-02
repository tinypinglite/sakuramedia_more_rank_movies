# SakuraMedia 更多影片榜单插件

为 SakuraMedia 提供独立的第三方 JAV 网站排行榜来源。当前接入
[Minnano AV](https://www.minnano-av.com/ranking_av.php?daily) 与
[JavLibrary](https://www.f101w.com/cn/)，后续其他网站以独立 board 加入同一个来源，
不影响现有 `sakuramedia_javdb_ranking` 插件。

## 榜单

来源 key：`more_rank_movies`

| board | 周期 | 说明 |
|---|---|---|
| `minnano_av` | `daily` / `weekly` / `monthly` | Minnano AV 热门榜 |
| `javlibrary_bestrated` | `monthly` / `all` | JavLibrary 高评价（上个月 / 全部） |
| `javlibrary_mostwanted` | `monthly` / `all` | JavLibrary 最想要（上个月 / 全部） |

Minnano AV 日榜、周榜、月榜分别对应：

- `https://www.minnano-av.com/ranking_av.php?daily`
- `https://www.minnano-av.com/ranking_av.php`
- `https://www.minnano-av.com/ranking_av.php?monthly`

JavLibrary 榜单固定使用 `https://www.f101w.com`，`mode=1` 为上个月、`mode=2` 为全部：

- 高评价 上个月：`https://www.f101w.com/cn/vl_bestrated.php?&mode=1&page=1`
- 高评价 全部：`https://www.f101w.com/cn/vl_bestrated.php?&mode=2&page=1`
- 最想要 上个月：`https://www.f101w.com/cn/vl_mostwanted.php?&mode=1&page=1`
- 最想要 全部：`https://www.f101w.com/cn/vl_mostwanted.php?&mode=2&page=1`

JavLibrary 每个榜单最多抓 25 页（约 500 条），番号直接取自列表页条目的 `div.id`，按序去重后交给宿主；
某页无条目即停止翻页，若整榜没有任何可用番号则失败并保留旧榜单，避免误清空数据。

Minnano AV 则从榜单中的作品详情页解析正式品番，再由宿主现有 JavDB 详情导入流程补齐影片资料。
DMM 商品链接中的 CID 仅用于定位榜单条目，不直接作为 JavDB 番号；没有可用作品详情或品番的条目会跳过，
若本轮没有任何可用正式品番则失败并保留旧榜单，避免误清空数据。

## 进度

全量任务按“同步排行榜周期”作为一个阶段，`current/total` 表示已完成的榜单周期数：
当前共 7 个周期（Minnano 日/周/月 + JavLibrary 高评价/最想要的上个月/全部），全量为 `0/7` 到 `7/7`，
手动单榜为 `0/1` 到 `1/1`。进度文本会同时显示成功、失败、待处理数量，
并在宿主处理周期期间约每 2 秒发送一次等待状态；`summary_patch` 使用整个任务的累计值。

## 任务

- 定时任务：`sakuramedia_more_rank_movies_sync`
  （`sync-more-rank-movies`），默认每天 01:45。
- 手动任务：`sakuramedia_more_rank_movies_sync_board`
  （`sync-more-rank-movies-board`），参数 `board_key` / `period`。
