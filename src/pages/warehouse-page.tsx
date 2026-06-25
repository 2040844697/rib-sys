import { Link } from "@tanstack/react-router";
import { Download, PackageCheck, Truck } from "lucide-react";

import { PageHeader, Surface } from "@/components/ui";

export function WarehousePage() {
  return (
    <div className="space-y-5">
      <PageHeader title="囤货工作台" description="囤货人处理入库、排发申请、国内运费和国内快递。" action={<button className="btn btn-secondary"><Download className="size-4" />导出</button>} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Link to="/app/warehouse/dispatch-requests" className="surface p-5 hover:border-cyan-300">
          <Truck className="size-5 text-cyan-700" />
          <h2 className="mt-3 font-semibold text-slate-950">排发申请处理</h2>
          <p className="mt-2 text-sm text-slate-600">核对、打包、录入国内运费和快递单号。</p>
        </Link>
        <Surface className="p-5">
          <PackageCheck className="size-5 text-cyan-700" />
          <h2 className="mt-3 font-semibold text-slate-950">国内入库</h2>
          <p className="mt-2 text-sm text-slate-600">后续接入国际批次入库和可排发库存生成。</p>
        </Surface>
      </div>
    </div>
  );
}
