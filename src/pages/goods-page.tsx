import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { SlidersHorizontal } from "lucide-react";

import { api } from "@/lib/api";
import { EmptyState, ErrorState, LoadingRows, PageHeader, SearchBox, SelectInput, StatusBadge, Surface } from "@/components/ui";

const matchModes = ["包含所选角色", "仅包含所选角色"];

export function GoodsPage() {
  const [keyword, setKeyword] = useState("");
  const [characterName, setCharacterName] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [matchMode, setMatchMode] = useState(matchModes[0]);

  const query = useQuery({
    queryKey: ["goods", keyword, characterName],
    queryFn: () => api.searchGoods({ keyword, characterName, pageSize: 30 }),
  });

  const characters = useMemo(() => {
    const values = new Set<string>();
    query.data?.items.forEach((item) => item.characterNames?.forEach((name) => values.add(name)));
    return Array.from(values);
  }, [query.data]);

  return (
    <div className="space-y-5">
      <PageHeader title="商品图鉴" description="重点支持查询和筛选。商品选择时也可以作为新建拼团页的小浮窗复用。" />
      <Surface className="p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="flex-1"><SearchBox value={keyword} onChange={setKeyword} placeholder="搜索商品名、别名、系列" /></div>
          <button className="btn btn-secondary" type="button" onClick={() => setFiltersOpen((value) => !value)}>
            <SlidersHorizontal className="size-4" />
            筛选
          </button>
        </div>
        {filtersOpen ? (
          <div className="mt-4 grid gap-3 border-t border-slate-200 pt-4 md:grid-cols-3">
            <SelectInput value={characterName} onChange={(event) => setCharacterName(event.target.value)}>
              <option value="">全部角色</option>
              {characters.map((name) => <option key={name} value={name}>{name}</option>)}
            </SelectInput>
            <SelectInput value={matchMode} onChange={(event) => setMatchMode(event.target.value)}>
              {matchModes.map((mode) => <option key={mode}>{mode}</option>)}
            </SelectInput>
            <SelectInput defaultValue="enabled">
              <option value="enabled">启用</option>
              <option value="draft">草稿</option>
              <option value="disabled">停用</option>
            </SelectInput>
          </div>
        ) : null}
      </Surface>

      {query.isLoading ? <LoadingRows rows={4} /> : null}
      {query.isError ? <ErrorState title="商品图鉴加载失败" description={query.error.message} /> : null}
      {query.data?.items.length === 0 ? <EmptyState title="暂无商品" description="当前筛选下没有商品。" /> : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {query.data?.items.map((item) => (
          <Link key={item.id} to="/app/goods/$goodsId" params={{ goodsId: item.id }}>
            <Surface className="overflow-hidden hover:border-cyan-300">
              <div className="flex aspect-square items-center justify-center bg-slate-100 text-4xl font-semibold text-cyan-800">
                {item.mainImageUrl ? <img src={item.mainImageUrl} alt="" className="size-full object-cover" /> : item.name.slice(0, 1)}
              </div>
              <div className="p-4">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-semibold text-slate-950">{item.name}</h3>
                  <StatusBadge value={item.status} />
                </div>
                <p className="mt-2 text-sm text-slate-500">{item.seriesName || "未分系列"}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {item.characterNames?.map((name) => <span className="badge-neutral" key={name}>{name}</span>)}
                </div>
              </div>
            </Surface>
          </Link>
        ))}
      </div>
    </div>
  );
}
