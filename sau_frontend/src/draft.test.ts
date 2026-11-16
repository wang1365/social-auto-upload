import { describe, expect, it } from "vitest";
import { fillItems, restoreDraft } from "./draft";

describe("发布草稿", () => {
  it("损坏或旧格式草稿不会阻止页面打开", () => {
    expect(restoreDraft("{corrupt").items).toEqual([]);
    expect(restoreDraft('{"items":null}').account_ids).toEqual([]);
  });
  it("去掉重复素材和账号，保留每条文案及提交标识", () => {
    const item = {
      material_id: 1,
      title: "视频一",
      description: "介绍",
      tags: ["测试"],
    };
    const value = restoreDraft(
      JSON.stringify({
        items: [item, item],
        account_ids: [2, 2, "invalid"],
        request_key: "stable-request",
      }),
    );
    expect(value.items).toEqual([item]);
    expect(value.account_ids).toEqual([2]);
    expect(value.request_key).toBe("stable-request");
  });
  it("批量填充话题不覆盖逐条标题，并且不共享可变数组", () => {
    const items = [1, 2].map((id) => ({
      material_id: id,
      title: `视频${id}`,
      description: "原正文",
      tags: ["旧话题"],
    }));
    const result = fillItems(items, { tags: ["新话题"], description: "" });
    expect(result.map((item) => item.title)).toEqual(["视频1", "视频2"]);
    expect(result[0].description).toBe("");
    result[0].tags.push("只改第一条");
    expect(result[1].tags).toEqual(["新话题"]);
    expect(items[0].tags).toEqual(["旧话题"]);
  });
});
