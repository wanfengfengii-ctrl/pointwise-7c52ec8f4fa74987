# 三稿接续核定

青榆口述史馆要把初稿标注经听校稿迁到定稿。发行时先选定稿件与公开摘录。夜班实收后才选标注词位，确认可以随后补交。在源库关闭后，同一件仍可分别提交两次核定并领取各自定稿。

## 发行和实收

新增 `issue.publish.publish_three_draft_packet(revisions, excerpts, old_excerpt_id, middle_revision_id, new_excerpt_id, *, packet_id=None) -> str`。初稿和定稿各引用一个已有许可摘录，听校稿给固定修订号。三份修订必须存在、互异且属于同一稿件，以调用给出的顺序作为两轮修订顺序。非法引用用 `ValueError` 拒绝。件号沿原入口规则，省略时由发行生成。

返回版本为 `2` 的 JSON 封套。封套绑定件号、同一稿件的有序三修订、首尾摘录及其公开出处和正文摘要。听校稿全篇及首尾片外的词值、逐词编码及出处留站。件内可以交匿名接续证据，证据的表示由实现决定。发行时还不知道查询词位和确认。两个公开摘录沿用原词位与出处口径。听校稿可含空段，也可没有词项。

封套沿用可信渠道交付。`ReceiptStore.accept(envelope)` 同时受理双稿和三稿件，核对封套声明、正文摘要、公开出处结构及所交证据的结构。成功返回原 `PacketReceipt` 形状，`body_digest` 为已核对的正文摘要。同件重收取原实收，包括重开离线库后重收。两种件共用件号含义，同号异件、损坏或声明与正文错绑用 `EnvelopeMismatch` 拒绝且不新增实收。`get_received(packet_id)` 仍按件号读取已实收件。

## 离线核定与领取

新增 `review.submit.submit_three_draft_review(receipts, archive, request) -> ArchiveEntry`，沿用 `ReviewRequest`、`OldAnnotation` 和 `Confirmation`。`request.packet_id` 指定本库的实收件，`annotations` 恰有一条，标注词位须在初稿摘录。确认引用本件首尾两侧公开词位，重复同对合并，空确认合法。两个核定入口各受理自己的件型。未知件、错件型、无效标注或超出摘录的确认用 `ValueError` 拒绝。

相邻两轮各按整稿匹配原值相等的词项，匹配严格保序且一对一。每轮每个未配对词项计 1，听校稿在两轮分别计费。只有两轮匹配使用听校稿中的同一次词出现，初稿词才可接续到定稿词。一份请求的全部确认必须在同一对完整对齐中兑现，总代价取满足确认的两轮代价和的最小值。没有这样的共同对齐时抛出原 `NoCompatibleAlignment`，不新增定稿或首执。

`report.details` 沿用双稿 `cost`、`annotations`、`confirmations`、`outcomes` 的含义与公开词项形状。`cost` 为整数。确认按初稿、定稿原序归并后存档。唯一一条标注结果的 `targets` 给出所有最优解中可到达的定稿公开词位，按定稿原序去重并保留原段出处。若存在最优解未接续到定稿、或接续到定稿片外，`can_have_no_public_landing` 为真。它可与非空 `targets` 同时成立。

报告的 `packet` 保留 `packet_id`、`body_digest` 及两侧摘录身份 `old`、`new`，并记录 `middle_revision_id` 和实际实收的 `receipt_id`。定稿快照与成功首执同次入账。签存失败沿用 SQLite 错误且无本次新增账，`archive.read.read_report(archive, report_id)` 在重开后返回固定报告和首执。双稿接口及旧报告照常使用。

## 交班样例

`three_draft_cases.py` 提供下表材料。词位下标按各稿的零基全文原序计算。`split-middle` 和 `shared-middle` 仅公开初稿下标 0 和定稿下标 1，其他样例的首尾稿全公开。

| 样例 | 初稿 / 听校稿 / 定稿 | 应签结果 |
| --- | --- | --- |
| `split-middle` | `A X` / `A X A` / `X A` | 查初稿 A，无确认签 2、无公开落点。确认首尾 A 后签 4、仅落到定稿下标 1。 |
| `shared-middle` | `A X` / `X A X` / `X A` | 查初稿 A，无确认签 2、仅落到定稿下标 1。 |
| `one-slot` | `A A` / `A` / `A A` | 查旧首 A，无确认签 2、定稿两个 A 都是公开落点，也可能无公开落点。两侧同序的任一对 A 单独确认可签 2，两对同时确认拒签。 |
| `different-witnesses` | `A B C` / `B C A B` / `A B C` | 首尾确认 A、B 或 B、C 都可成立，一次确认 A、B、C 须拒签。 |
| `empty-middle` | `A` / 空 / `A` | 无确认签 2、无公开落点，确认首尾 A 须拒签。 |

夹具用 `source_desk(database, case_name)` 打开源库并返回修订库、许可库和发件参数，退出时关闭源库。`offline_desk(database)` 打开独立离线库，返回实收和归档对象。传入同一路径即可在后续步骤重开离线库。`python3 -B three_draft_cases.py` 核对夹具导入与许可摘录。原完整双稿回归可用 `python3 -B check_project.py` 运行。

沿用 `.pointwise-runtime.json`。其中 `version` 为 1，`kind` 为 `cli`，`setup` 记录准备命令列表，`verify` 和 `demo` 各为一条命令，所有命令用 argv 数组。把原双稿回归和三稿业务核验接入 `verify`，核验失败须非零退出。用 `demo` 展示 `split-middle` 在关闭源库后分别签出两次结论、重开后按号领回。
