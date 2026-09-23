delete from users *;
delete from bins *;
delete from devices *;

insert into users (email, password_hash)
values ('test@skibidi.com', '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8');

insert into devices (mac, owner_id, created_at, is_active)
values ('00:1A:2B:3C:4D:5E', (select id from users limit 1), now(), true);

insert into bins (location, user_id, name, created_at)
values ('Mataram, Lombok, Indonesia', (select id from users limit 1), 'UNRAM_bin_1', now());

select * from users;