-- Postgres only. Column comments are read by the agent and passed to the model with the schema,
-- the same way it would pick up comments on a Snowflake table.

COMMENT ON TABLE branches IS 'Bank branches; each customer is assigned to one';
COMMENT ON TABLE customers IS 'One row per customer';
COMMENT ON COLUMN customers.segment IS 'retail, premier, or small_business';
COMMENT ON TABLE accounts IS 'Deposit and credit card accounts; a customer can have several';
COMMENT ON COLUMN accounts.account_type IS 'checking, savings, or credit_card';
COMMENT ON COLUMN accounts.status IS 'open or closed';
COMMENT ON COLUMN accounts.balance IS 'Current balance; negative on a credit card means the customer owes money';
COMMENT ON TABLE transactions IS 'Posted transactions, April through September 2026';
COMMENT ON COLUMN transactions.amount IS 'Positive = money in, negative = money out';
COMMENT ON COLUMN transactions.txn_type IS 'deposit, card_purchase, transfer_in, transfer_out, fee, interest, or card_payment';
COMMENT ON COLUMN transactions.merchant IS 'Set for card purchases, payroll deposits, and bills (rent, mortgage, auto loan)';
