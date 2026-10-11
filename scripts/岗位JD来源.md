# 初始化岗位 JD 来源

检索日期：2026-10-11。以下公开招聘信息用于归纳职责和技能，模板为通用化改写，不代表来源企业正在招聘，也不照搬其薪资、地点、学历或工作年限要求。

| 初始化岗位 | 参考公开 JD |
| --- | --- |
| Java开发 | [百度：Java研发工程师（J96053）](https://talent.baidu.com/jobs/detail/SOCIAL/1a10a01a-c015-44ea-a88a-3b028158288a) |
| Golang开发 | [腾讯：AI协作工具产品后台研发高级工程师](https://careers.tencent.com/zh-cn/jobdesc.html?postId=2061001586997637120) |
| Agent开发 | [飞派科技：AI Agent研发工程师（社招）](https://www.flypai.com/jobs.html) |
| 大模型算法研发 | [美的：大模型应用算法中级工程师](https://recruit.midea.com/recruitOut/ihr/social/jobApplication?positionId=8b8b3256a06c3b3001a0803d69592fc5) |
| 技术运营 | [道旅科技：技术运营，河北工业大学就业网](https://career.hebut.edu.cn/home/correcruit/content/id/71068.html) |
| 前端开发 | [百度：前端研发工程师（J96580）](https://talent.baidu.com/jobs/detail/SOCIAL/afc332f3-513b-40a4-ba33-6a52878999e1) |
| 测试开发 | [百度：北京-AI测试开发工程师（J101055）](https://talent.baidu.com/jobs/detail/GRADUATE/6061be03-f92b-4430-a1b8-9168de0f91f6) |
| 人力资源专员 | [云意电气：人力资源专员，河北工业大学就业网](https://career.hebut.edu.cn/home/correcruit/content/id/80039.html) |

## 适配说明

- 技术运营归纳为系统与接口运行支持、指标分析和跨团队异常处理，去掉酒店行业及英语等级要求。
- Golang开发从腾讯高级后台岗位抽取通用能力，去掉五年经验门槛。
- 测试开发以通用自动化与质量能力为必须项，将大模型与Agent专项测试设为加分项。
- 其余岗位同样只保留适合本工具的能力要求；课程、个人项目、实习中的可验证成果可以作为评估证据。
- 必须项与加分项划分、权重和评分规则由本项目设计，公开JD本身未提供这些分值。每个岗位四项必须项分别25、20、20、15分，两项加分项各10分，总分100。
- 必须项不满足仍保留人工推进；未提供证据标记待核实，不直接认定不满足。

数据在`job_seed_data.py`的`ROLES`中维护，`build_jobs()`生成岗位JD和结构化评分项；完整来源同时写入每个岗位JD。
