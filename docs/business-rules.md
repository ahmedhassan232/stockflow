# Business rules

These rules are enforced by the backend (and covered by `backend/tests`). The UI only
previews them; the server's figures are always the ones stored and printed.

## Numbers
- Money `NUMERIC(14,2)`, unit cost `NUMERIC(14,4)`, quantity `NUMERIC(14,3)`, rates `NUMERIC(5,2)`.
- Rounding is ROUND_HALF_UP, applied per invoice line. No floating point anywhere:
  the API sends and receives decimal strings; the browser previews with BigInt arithmetic.

## Prices, discount, tax
- Prices are tax-exclusive. Line net = quantity × unit price − discount.
- Tax is calculated per line on the discounted amount, using the product's tax rate at
  the time of sale (stored on the line). A discount larger than the line → `DISCOUNT_TOO_LARGE`.

## Stock
- The only way stock changes is the stock ledger: every change writes one immutable
  movement row (type, quantity in/out, unit cost, balance after, reference document).
- Balances are locked row-by-row while they change, so two cashiers cannot sell the same
  last unit. Selling more than available → `INSUFFICIENT_STOCK` (unless the company
  enables "allow negative stock").
- Cost is the weighted average: each receipt recalculates
  `(old qty × old avg + received qty × unit cost) / new qty`. Sales, returns to supplier
  and outgoing adjustments leave the average unchanged. The average is never editable.
- Each sale line stores the average cost at the moment of sale (`unit_cost_at_sale`);
  profit reports use that stored value, so later purchases never change past profit.

## Purchasing
- draft → ordered → partially received → received; draft/ordered orders can be cancelled
  if nothing was received or paid. Receiving more than ordered → `OVER_RECEIPT`.
- Returning to the supplier is limited to what was received and is still in stock.
- Supplier payments cannot exceed the outstanding balance (`OVERPAYMENT`).

## Sales
- An invoice is posted in one transaction: lines, stock movements, payments, numbering.
- Change is given only from cash. Paying less than the total requires a customer
  (credit sale) → otherwise `CUSTOMER_REQUIRED`.
- Returns: per line, up to the quantity not yet returned; stock comes back at the cost
  recorded on the sale; the refund is the returned value minus what the customer still owes.
- Voiding returns everything and refunds everything; not allowed after a partial return.
- Posted invoices are never edited or deleted.

## Idempotency
- POS checkout, payments, receipts, returns, adjustments and transfers accept an
  `Idempotency-Key` header. Repeating a request with the same key returns the first
  result and never creates a second document or stock movement.

## Reports
- Gross sales = invoice totals including tax. Revenue = Σ(subtotal − discount) of
  completed sales, excluding tax, minus returns. COGS from `unit_cost_at_sale`.
  Gross profit = revenue − COGS. Days are bucketed in the company's time zone.
- Changing the company currency changes display only; amounts are not converted.

## Notifications
- A low-stock notification is raised when a balance is at or below its minimum level
  (minimum 0 = no alert): immediately on a sale, and by a scan every 15 minutes for all
  other causes. Only one open notification exists per warehouse + product.

## Expenses and net profit
- An expense has a date, category, amount and payment method; optionally a branch.
  It cannot be edited or deleted: a mistake is voided (reason required) and re-entered.
- Net profit = gross profit − active expenses dated in the period. It is shown only for
  the whole company (not when a report is filtered by warehouse).

## Exports
- CSV files are UTF-8 with BOM (Excel reads Arabic correctly). Text cells starting with
  `= + - @` are prefixed with an apostrophe so a name can never run as a formula.
- Cost and stock value columns appear only for users holding `reports.inventory.view`.

## Platform administration
- A platform administrator can list companies and suspend / re-activate them, nothing
  else: no access to any company's business data. Suspension takes effect on the next
  request of every member; data is kept.
