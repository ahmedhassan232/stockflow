/** API shapes. Every amount/quantity is a decimal STRING exactly as the server sent it. */
export interface Named {
  id: string;
  name: string;
  is_active: boolean;
}
export interface Product extends Named {
  sku: string;
  barcode: string | null;
  category_id: string | null;
  unit_id: string | null;
  description: string | null;
  purchase_price: string;
  selling_price: string;
  average_cost: string;
  tax_rate: string;
  track_inventory: boolean;
}
export interface Party extends Named {
  phone: string | null;
  email: string | null;
  address: string | null;
  tax_number: string | null;
  notes: string | null;
}
export interface WarehouseItem extends Named {
  code: string;
  branch_id: string | null;
}
export interface Balance {
  id: string;
  warehouse_id: string;
  warehouse_name: string;
  product_id: string;
  product_name: string;
  sku: string;
  quantity: string;
  minimum_stock_level: string;
  is_low: boolean;
}
export interface Movement {
  id: string;
  product_id: string;
  warehouse_id: string;
  movement_type: string;
  quantity_in: string;
  quantity_out: string;
  unit_cost: string;
  balance_after: string;
  reference_type: string;
  reason: string | null;
  created_at: string;
}
export interface PurchaseItem {
  id: string;
  line_no: number;
  product_id: string;
  product_name: string;
  sku: string;
  quantity: string;
  unit_cost: string;
  tax_rate: string;
  line_total: string;
  received_quantity: string;
  returned_quantity: string;
}
export interface Purchase {
  id: string;
  number: string;
  supplier_id: string;
  supplier_name: string;
  warehouse_id: string;
  warehouse_name: string;
  status: "draft" | "ordered" | "partially_received" | "received" | "cancelled";
  subtotal: string;
  tax_amount: string;
  total: string;
  paid_amount: string;
  balance_due: string;
  notes: string | null;
  created_at: string;
  items?: PurchaseItem[];
}
export interface SaleItem {
  id: string;
  line_no: number;
  product_id: string;
  product_name: string;
  quantity: string;
  unit_price: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  line_total: string;
  returned_quantity: string;
}
export interface Payment {
  id: string;
  direction: "in" | "out";
  method: string;
  amount: string;
  reference: string | null;
  created_at: string;
}
export interface Sale {
  id: string;
  number: string;
  customer_id: string | null;
  customer_name: string | null;
  warehouse_id: string;
  warehouse_name: string;
  status: "completed" | "cancelled";
  payment_status: "paid" | "partial" | "unpaid" | "cancelled";
  subtotal: string;
  discount_amount: string;
  tax_amount: string;
  total: string;
  paid_amount: string;
  returned_amount: string;
  balance_due: string;
  notes: string | null;
  created_at: string;
  items?: SaleItem[];
  payments?: Payment[];
  cashier_name?: string;
  change_due?: string;
  refund_amount?: string;
}
export const PAYMENT_METHODS = ["cash", "card", "bank_transfer", "wallet"] as const;
