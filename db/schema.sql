DROP TABLE IF EXISTS bookings, inventory, opportunities, products, accounts, sales_reps;

CREATE TABLE sales_reps (
    rep_id     integer PRIMARY KEY,
    full_name  text NOT NULL,
    email      text NOT NULL UNIQUE,
    region     text NOT NULL,
    hire_date  date NOT NULL
);

CREATE TABLE accounts (
    account_id    integer PRIMARY KEY,
    account_name  text NOT NULL UNIQUE,
    industry      text NOT NULL,
    owner_rep_id  integer NOT NULL REFERENCES sales_reps(rep_id),
    created_date  date NOT NULL
);


CREATE TABLE products (
    product_id    integer PRIMARY KEY,
    product_name  text NOT NULL UNIQUE,
    channel       text NOT NULL CHECK (channel IN ('newsletter', 'podcast', 'video', 'web', 'social')),
    list_price    numeric(12,2) NOT NULL CHECK (list_price > 0)  -- price per placement, USD
);

CREATE TABLE opportunities (
    opportunity_id       integer PRIMARY KEY,
    account_id           integer NOT NULL REFERENCES accounts(account_id),
    owner_rep_id         integer NOT NULL REFERENCES sales_reps(rep_id),
    opportunity_name     text NOT NULL,
    stage                text NOT NULL CHECK (stage IN ('prospecting', 'qualification', 'proposal',
                                                        'negotiation', 'closed_won', 'closed_lost')),
    amount               numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_date         date NOT NULL,
    expected_close_date  date NOT NULL,
    closed_date          date,
    last_activity_date   date NOT NULL CHECK (last_activity_date >= created_date),
    -- a deal has a closed_date exactly when it is closed won or closed lost
    CHECK ((stage IN ('closed_won', 'closed_lost')) = (closed_date IS NOT NULL))
);

CREATE TABLE inventory (
    product_id        integer NOT NULL REFERENCES products(product_id),
    inventory_month   date NOT NULL CHECK (extract(day FROM inventory_month) = 1),
    total_placements  integer NOT NULL CHECK (total_placements >= 0),
    PRIMARY KEY (product_id, inventory_month)
);

CREATE TABLE bookings (
    booking_id      integer PRIMARY KEY,
    opportunity_id  integer NOT NULL REFERENCES opportunities(opportunity_id),
    product_id      integer NOT NULL REFERENCES products(product_id),
    booking_date    date NOT NULL,
    delivery_month  date NOT NULL CHECK (extract(day FROM delivery_month) = 1),
    placements      integer NOT NULL CHECK (placements > 0),
    amount          numeric(12,2) NOT NULL CHECK (amount >= 0),
    status          text NOT NULL CHECK (status IN ('active', 'cancelled')),
    -- one line item per deal, product and delivery month
    UNIQUE (opportunity_id, product_id, delivery_month),
    -- every booked month must have inventory for that product
    FOREIGN KEY (product_id, delivery_month) REFERENCES inventory(product_id, inventory_month)
);