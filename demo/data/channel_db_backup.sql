--
-- PostgreSQL database dump
--

\restrict Iiz3r1jkhklhAa04RbFID56dnSvLJB5Mm7BxZvwlopp1xoXfXyuNskoPW8VaQ69

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: dtc_orders; Type: TABLE; Schema: public; Owner: omni
--

CREATE TABLE public.dtc_orders (
    id text NOT NULL,
    ts text NOT NULL,
    sku text NOT NULL,
    qty integer NOT NULL,
    fulfilled_qty integer DEFAULT 0 NOT NULL,
    status text NOT NULL,
    partial_shipments text DEFAULT '[]'::text NOT NULL,
    CONSTRAINT dtc_orders_qty_check CHECK ((qty > 0))
);


ALTER TABLE public.dtc_orders OWNER TO omni;

--
-- Name: etsy_orders; Type: TABLE; Schema: public; Owner: omni
--

CREATE TABLE public.etsy_orders (
    id text NOT NULL,
    ts text NOT NULL,
    sku text NOT NULL,
    qty integer NOT NULL,
    fulfilled_qty integer DEFAULT 0 NOT NULL,
    status text NOT NULL,
    partial_shipments text DEFAULT '[]'::text NOT NULL,
    CONSTRAINT dtc_orders_qty_check CHECK ((qty > 0))
);


ALTER TABLE public.etsy_orders OWNER TO omni;

--
-- Name: walmart_orders; Type: TABLE; Schema: public; Owner: omni
--

CREATE TABLE public.walmart_orders (
    id text NOT NULL,
    ts text NOT NULL,
    sku text NOT NULL,
    qty integer NOT NULL,
    fulfilled_qty integer DEFAULT 0 NOT NULL,
    status text NOT NULL,
    partial_shipments text DEFAULT '[]'::text NOT NULL,
    CONSTRAINT dtc_orders_qty_check CHECK ((qty > 0))
);


ALTER TABLE public.walmart_orders OWNER TO omni;

--
-- Data for Name: dtc_orders; Type: TABLE DATA; Schema: public; Owner: omni
--

COPY public.dtc_orders (id, ts, sku, qty, fulfilled_qty, status, partial_shipments) FROM stdin;
20f1bbc2	2026-10-25T02:50:16Z	MUG-001	1	0	open	[]
cb89aa62	2026-10-25T02:50:35Z	MUG-001	50	0	open	[]
67572c38	2026-10-25T02:50:50Z	LAMP-002	25	25	fulfilled	[]
\.


--
-- Data for Name: etsy_orders; Type: TABLE DATA; Schema: public; Owner: omni
--

COPY public.etsy_orders (id, ts, sku, qty, fulfilled_qty, status, partial_shipments) FROM stdin;
0d936269	2026-10-25T03:43:47Z	KBD-003	2	0	open	[]
\.


--
-- Data for Name: walmart_orders; Type: TABLE DATA; Schema: public; Owner: omni
--

COPY public.walmart_orders (id, ts, sku, qty, fulfilled_qty, status, partial_shipments) FROM stdin;
\.


--
-- Name: dtc_orders dtc_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: omni
--

ALTER TABLE ONLY public.dtc_orders
    ADD CONSTRAINT dtc_orders_pkey PRIMARY KEY (id);


--
-- Name: etsy_orders etsy_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: omni
--

ALTER TABLE ONLY public.etsy_orders
    ADD CONSTRAINT etsy_orders_pkey PRIMARY KEY (id);


--
-- Name: walmart_orders walmart_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: omni
--

ALTER TABLE ONLY public.walmart_orders
    ADD CONSTRAINT walmart_orders_pkey PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict Iiz3r1jkhklhAa04RbFID56dnSvLJB5Mm7BxZvwlopp1xoXfXyuNskoPW8VaQ69

