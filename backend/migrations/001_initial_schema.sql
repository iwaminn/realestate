--
-- PostgreSQL database dump
--

-- Dumped from database version 15.13 (Debian 15.13-1.pgdg120+1)
-- Dumped by pg_dump version 15.13 (Debian 15.13-1.pgdg120+1)

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
-- Name: building_aliases; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.building_aliases (
    id integer NOT NULL,
    building_id integer NOT NULL,
    alias_name character varying(255) NOT NULL,
    source character varying(50),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.building_aliases OWNER TO realestate;

--
-- Name: building_aliases_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.building_aliases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.building_aliases_id_seq OWNER TO realestate;

--
-- Name: building_aliases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.building_aliases_id_seq OWNED BY public.building_aliases.id;


--
-- Name: buildings; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.buildings (
    id integer NOT NULL,
    normalized_name character varying(255) NOT NULL,
    address character varying(500),
    total_floors integer,
    built_year integer,
    structure character varying(100),
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.buildings OWNER TO realestate;

--
-- Name: buildings_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.buildings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.buildings_id_seq OWNER TO realestate;

--
-- Name: buildings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.buildings_id_seq OWNED BY public.buildings.id;


--
-- Name: listing_price_history; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.listing_price_history (
    id integer NOT NULL,
    property_listing_id integer NOT NULL,
    price integer NOT NULL,
    management_fee integer,
    repair_fund integer,
    recorded_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.listing_price_history OWNER TO realestate;

--
-- Name: listing_price_history_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.listing_price_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.listing_price_history_id_seq OWNER TO realestate;

--
-- Name: listing_price_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.listing_price_history_id_seq OWNED BY public.listing_price_history.id;


--
-- Name: master_properties; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.master_properties (
    id integer NOT NULL,
    building_id integer NOT NULL,
    room_number character varying(50),
    floor_number integer,
    area double precision,
    layout character varying(50),
    direction character varying(50),
    property_hash character varying(255),
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.master_properties OWNER TO realestate;

--
-- Name: master_properties_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.master_properties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.master_properties_id_seq OWNER TO realestate;

--
-- Name: master_properties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.master_properties_id_seq OWNED BY public.master_properties.id;


--
-- Name: price_history; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.price_history (
    id integer NOT NULL,
    property_id integer,
    price integer NOT NULL,
    date_recorded timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.price_history OWNER TO realestate;

--
-- Name: price_history_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.price_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.price_history_id_seq OWNER TO realestate;

--
-- Name: price_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.price_history_id_seq OWNED BY public.price_history.id;


--
-- Name: properties; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.properties (
    id integer NOT NULL,
    site_property_id character varying,
    title character varying NOT NULL,
    building_name character varying,
    room_number character varying,
    price integer,
    address character varying,
    area double precision,
    layout character varying,
    station_info text,
    description text,
    source character varying,
    url character varying,
    floor_number integer,
    total_floors integer,
    direction character varying,
    property_hash character varying,
    building_hash character varying,
    last_scraped_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.properties OWNER TO realestate;

--
-- Name: properties_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.properties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.properties_id_seq OWNER TO realestate;

--
-- Name: properties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.properties_id_seq OWNED BY public.properties.id;


--
-- Name: property_images; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.property_images (
    id integer NOT NULL,
    property_listing_id integer NOT NULL,
    image_url character varying(1000),
    image_type character varying(50),
    display_order integer,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.property_images OWNER TO realestate;

--
-- Name: property_images_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.property_images_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.property_images_id_seq OWNER TO realestate;

--
-- Name: property_images_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.property_images_id_seq OWNED BY public.property_images.id;


--
-- Name: property_listings; Type: TABLE; Schema: public; Owner: realestate
--

CREATE TABLE public.property_listings (
    id integer NOT NULL,
    master_property_id integer NOT NULL,
    source_site character varying(50) NOT NULL,
    site_property_id character varying(255),
    url character varying(1000) NOT NULL,
    title character varying(500),
    description text,
    agency_name character varying(255),
    agency_tel character varying(50),
    current_price integer,
    management_fee integer,
    repair_fund integer,
    station_info text,
    features text,
    is_active boolean,
    first_seen_at timestamp without time zone DEFAULT now(),
    last_scraped_at timestamp without time zone DEFAULT now(),
    delisted_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    last_fetched_at timestamp without time zone DEFAULT now(),
    last_confirmed_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.property_listings OWNER TO realestate;

--
-- Name: property_listings_id_seq; Type: SEQUENCE; Schema: public; Owner: realestate
--

CREATE SEQUENCE public.property_listings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.property_listings_id_seq OWNER TO realestate;

--
-- Name: property_listings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: realestate
--

ALTER SEQUENCE public.property_listings_id_seq OWNED BY public.property_listings.id;


--
-- Name: building_aliases id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.building_aliases ALTER COLUMN id SET DEFAULT nextval('public.building_aliases_id_seq'::regclass);


--
-- Name: buildings id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.buildings ALTER COLUMN id SET DEFAULT nextval('public.buildings_id_seq'::regclass);


--
-- Name: listing_price_history id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.listing_price_history ALTER COLUMN id SET DEFAULT nextval('public.listing_price_history_id_seq'::regclass);


--
-- Name: master_properties id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.master_properties ALTER COLUMN id SET DEFAULT nextval('public.master_properties_id_seq'::regclass);


--
-- Name: price_history id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.price_history ALTER COLUMN id SET DEFAULT nextval('public.price_history_id_seq'::regclass);


--
-- Name: properties id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.properties ALTER COLUMN id SET DEFAULT nextval('public.properties_id_seq'::regclass);


--
-- Name: property_images id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.property_images ALTER COLUMN id SET DEFAULT nextval('public.property_images_id_seq'::regclass);


--
-- Name: property_listings id; Type: DEFAULT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.property_listings ALTER COLUMN id SET DEFAULT nextval('public.property_listings_id_seq'::regclass);


--
-- Name: building_aliases building_aliases_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.building_aliases
    ADD CONSTRAINT building_aliases_pkey PRIMARY KEY (id);


--
-- Name: buildings buildings_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.buildings
    ADD CONSTRAINT buildings_pkey PRIMARY KEY (id);


--
-- Name: listing_price_history listing_price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.listing_price_history
    ADD CONSTRAINT listing_price_history_pkey PRIMARY KEY (id);


--
-- Name: master_properties master_properties_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.master_properties
    ADD CONSTRAINT master_properties_pkey PRIMARY KEY (id);


--
-- Name: master_properties master_properties_property_hash_key; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.master_properties
    ADD CONSTRAINT master_properties_property_hash_key UNIQUE (property_hash);


--
-- Name: price_history price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_pkey PRIMARY KEY (id);


--
-- Name: properties properties_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_pkey PRIMARY KEY (id);


--
-- Name: properties properties_property_hash_key; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_property_hash_key UNIQUE (property_hash);


--
-- Name: property_images property_images_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.property_images
    ADD CONSTRAINT property_images_pkey PRIMARY KEY (id);


--
-- Name: property_listings property_listings_pkey; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.property_listings
    ADD CONSTRAINT property_listings_pkey PRIMARY KEY (id);


--
-- Name: property_listings property_listings_url_key; Type: CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.property_listings
    ADD CONSTRAINT property_listings_url_key UNIQUE (url);


--
-- Name: idx_building_aliases_alias_name; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_building_aliases_alias_name ON public.building_aliases USING btree (alias_name);


--
-- Name: idx_building_aliases_building_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_building_aliases_building_id ON public.building_aliases USING btree (building_id);


--
-- Name: idx_buildings_address; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_buildings_address ON public.buildings USING btree (address);


--
-- Name: idx_buildings_normalized_name; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_buildings_normalized_name ON public.buildings USING btree (normalized_name);


--
-- Name: idx_listing_price_history_property_listing_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_listing_price_history_property_listing_id ON public.listing_price_history USING btree (property_listing_id);


--
-- Name: idx_listing_price_history_recorded_at; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_listing_price_history_recorded_at ON public.listing_price_history USING btree (recorded_at);


--
-- Name: idx_master_properties_building_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_master_properties_building_id ON public.master_properties USING btree (building_id);


--
-- Name: idx_master_properties_property_hash; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_master_properties_property_hash ON public.master_properties USING btree (property_hash);


--
-- Name: idx_price_history_property_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_price_history_property_id ON public.price_history USING btree (property_id);


--
-- Name: idx_properties_building_hash; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_properties_building_hash ON public.properties USING btree (building_hash);


--
-- Name: idx_properties_price; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_properties_price ON public.properties USING btree (price);


--
-- Name: idx_properties_source; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_properties_source ON public.properties USING btree (source);


--
-- Name: idx_property_images_property_listing_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_property_images_property_listing_id ON public.property_images USING btree (property_listing_id);


--
-- Name: idx_property_listings_is_active; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_property_listings_is_active ON public.property_listings USING btree (is_active);


--
-- Name: idx_property_listings_master_property_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_property_listings_master_property_id ON public.property_listings USING btree (master_property_id);


--
-- Name: idx_property_listings_source_site; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX idx_property_listings_source_site ON public.property_listings USING btree (source_site);


--
-- Name: ix_building_aliases_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX ix_building_aliases_id ON public.building_aliases USING btree (id);


--
-- Name: ix_buildings_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX ix_buildings_id ON public.buildings USING btree (id);


--
-- Name: ix_listing_price_history_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX ix_listing_price_history_id ON public.listing_price_history USING btree (id);


--
-- Name: ix_master_properties_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX ix_master_properties_id ON public.master_properties USING btree (id);


--
-- Name: ix_property_images_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX ix_property_images_id ON public.property_images USING btree (id);


--
-- Name: ix_property_listings_id; Type: INDEX; Schema: public; Owner: realestate
--

CREATE INDEX ix_property_listings_id ON public.property_listings USING btree (id);


--
-- Name: building_aliases building_aliases_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.building_aliases
    ADD CONSTRAINT building_aliases_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: listing_price_history listing_price_history_property_listing_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.listing_price_history
    ADD CONSTRAINT listing_price_history_property_listing_id_fkey FOREIGN KEY (property_listing_id) REFERENCES public.property_listings(id);


--
-- Name: master_properties master_properties_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.master_properties
    ADD CONSTRAINT master_properties_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: price_history price_history_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: property_images property_images_property_listing_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.property_images
    ADD CONSTRAINT property_images_property_listing_id_fkey FOREIGN KEY (property_listing_id) REFERENCES public.property_listings(id);


--
-- Name: property_listings property_listings_master_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: realestate
--

ALTER TABLE ONLY public.property_listings
    ADD CONSTRAINT property_listings_master_property_id_fkey FOREIGN KEY (master_property_id) REFERENCES public.master_properties(id);


--
-- PostgreSQL database dump complete
--

