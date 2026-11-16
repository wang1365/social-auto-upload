import type { PublishItem } from "./api";

export interface Draft {
  items: PublishItem[];
  account_ids: number[];
  request_key: string;
}
export const emptyDraft = (): Draft => ({
  items: [],
  account_ids: [],
  request_key: crypto.randomUUID(),
});
export function restoreDraft(raw: string | null): Draft {
  try {
    const value = JSON.parse(raw || "null");
    if (
      !value ||
      !Array.isArray(value.items) ||
      !Array.isArray(value.account_ids)
    )
      return emptyDraft();
    const ids = new Set<number>();
    const items = value.items
      .filter((item: PublishItem) => {
        if (
          !Number.isInteger(item.material_id) ||
          ids.has(item.material_id) ||
          typeof item.title !== "string" ||
          typeof item.description !== "string" ||
          !Array.isArray(item.tags)
        )
          return false;
        ids.add(item.material_id);
        return true;
      })
      .slice(0, 100);
    return {
      items,
      account_ids: [
        ...new Set<number>(value.account_ids.filter(Number.isInteger)),
      ],
      request_key:
        typeof value.request_key === "string" && value.request_key.length >= 8
          ? value.request_key
          : crypto.randomUUID(),
    };
  } catch {
    return emptyDraft();
  }
}
export function fillItems(
  items: PublishItem[],
  values: { title?: string; description?: string; tags?: string[] },
) {
  return items.map((item) => ({
    ...item,
    ...values,
    tags: values.tags ? [...values.tags] : item.tags,
  }));
}
