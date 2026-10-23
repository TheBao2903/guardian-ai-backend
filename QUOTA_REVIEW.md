# Rà soát quota Firestore — 23/10/2026

## Kết luận

Log `429 Quota exceeded` xác nhận Firestore từ chối yêu cầu vì quota. Chưa truy cập
Firebase Console nên chưa xác định được metric quota cụ thể hoặc tổng usage thực tế.
Code có nguồn đọc nền lớn ngay cả khi không có người dùng: hai worker quét mỗi
0,5 giây. Bản sửa chuyển danh sách ứng viên sang listener, giữ transaction làm nơi
quyết định nghiệp vụ, giữ chu kỳ xử lý và đối soát database mỗi 60 giây.

## Các luồng và cách xử lý

| Luồng | Hiện trạng trước sửa | Thay đổi / lý do giữ |
| --- | --- | --- |
| Audio alert worker | Hai query mỗi khoảng 0,5 giây, kể cả rỗng | Hai listener query theo status; đọc snapshot trong RAM mỗi 0,5 giây; đọc đối soát mỗi 60 giây |
| Delivery retry / dispatch lease | Đọc transaction mỗi tick ngay cả job chưa đến giờ hoặc còn lease | Lọc thời điểm từ snapshot trước; transaction vẫn kiểm tra lại lease, trạng thái, phiên SOS và ownership khi thực thi |
| Safety Check scheduler | Mỗi 30 giây đọc lại tất cả phiên ACTIVE/CHECK_REQUIRED | Listener theo đúng bộ lọc cũ, scheduler vẫn xét deadline mỗi 30 giây, đối soát mỗi 60 giây; giữ hỗ trợ deadline datetime/ISO |
| Health check | Liệt kê mọi collection, SDK retry có thể chờ 60 giây; gọi đồng bộ trong async endpoint | Một document read với timeout 2 giây, không SDK retry; dùng worker thread; chia sẻ kết quả tốt 15 giây, lỗi 5 giây |
| Lịch sử SOS | Thiếu import `Query`, luôn rơi vào fallback đọc toàn bộ lịch sử | Bổ sung import để query có order và limit thực sự chạy |
| Fallback lịch sử SOS / detection / recording / location | Khi 429 vẫn có thể chạy thêm query rộng hơn | Truyền lỗi 429 lên caller; không dùng query rộng để thử chữa hết quota; giữ fallback cho các lỗi khác |
| Trạng thái audio từ Flutter | Polling mỗi giây sau đăng nhập, kể cả không có cảnh báo | WebSocket dùng chung listener theo user/process; đồng bộ ban đầu, khi resume/reconnect; chỉ polling mỗi giây khi realtime lỗi |
| Xác thực mỗi protected request | Đọc hồ sơ user để kiểm tra status và role | Giữ đọc thật, tránh cache khiến tài khoản đã khóa vẫn được phép thao tác |
| Recording idempotency | Đọc tối đa 100 recording gần nhất khi upload | Giữ cửa sổ và quy tắc hiện tại; tối ưu bằng index theo event cần kiểm thử/migration riêng |
| Contacts và hồ sơ y tế | Một số read trước/sau write; đọc hồ sơ hiện tại khi SOS | Giữ để không thay đổi dữ liệu trả về khi cập nhật đồng thời hoặc lựa chọn chia sẻ thông tin y tế |
| AI audio / realtime GPS | Inference window không lưu Firestore; broadcast vị trí dùng RAM/WebSocket | Đã tránh ghi liên tục, không sửa |
| Seed Safety Check templates | Kiểm tra 5 document ở mỗi process startup | Chi phí nhỏ, giữ khả năng tự khởi tạo dữ liệu mặc định |

## Ước lượng tiết kiệm

Giả sử một process chạy 24 giờ, database rỗng, query nhanh, listener ổn định:

- Hai query worker: khoảng `2 × 2 × 86.400 = 345.600` query/ngày trước sửa.
- Sau sửa: khoảng `2 × 1.440 = 2.880` query đối soát/ngày, giảm khoảng **99,17%**
  riêng phần query định kỳ. Còn phí khởi tạo listener, thay đổi document, reconnect
  và transaction khi có công việc. Đây không phải mức giảm đã đo trên production.
- Scheduler Safety Check: khoảng 2.880 query/ngày xuống khoảng 1.440 query đối soát
  mỗi ngày với chu kỳ mặc định 30 giây. Dữ liệu active được cập nhật qua listener.
- Health check liên tục: tối đa khoảng 5.760 probe thành công/ngày/process nhờ
  cache 15 giây. `/health` vẫn báo 503 khi probe Firestore lỗi hoặc model chưa sẵn sàng.
- Query đối soát trả nhiều document vẫn tính nhiều lượt đọc. Các listener cũng
  tính phí khi document vào/đổi/rời tập kết quả. Không có cam kết tổng quota cố định.

Nguồn chính thức: [Firestore billing](https://firebase.google.com/docs/firestore/pricing),
[Firestore quotas](https://firebase.google.com/docs/firestore/quotas),
[Render health checks](https://render.com/docs/health-checks).

## Ranh giới nghiệp vụ và phục hồi

- Giữ deadline 10 giây, quy tắc cancel đúng hạn / confirm / timeout, trạng thái API,
  idempotency key, giới hạn người nhận, nội dung thông báo và privacy.
- Listener chỉ cung cấp ứng viên; transaction đọc lại dữ liệu Firestore để quyết
  định. Snapshot cũ không được quyền tạo SOS, vượt lease hay gửi job đã hoàn tất.
- Không cache kết quả xác thực, hồ sơ y tế hoặc response trạng thái của API.
- Khi restart, listener và query khởi tạo đọc lại công việc còn lưu trên Firestore.
- Listener chết được nối lại; nếu thiết lập listener thất bại thì dùng query trực
  tiếp. Nối lại có backoff. Nếu stream trông còn hoạt động nhưng ngừng cập nhật,
  lần đối soát tiếp theo phát hiện thay đổi trong khoảng 60 giây cộng thời gian RPC.
- Lỗi vòng lặp audio worker được backoff khoảng 1, 2, 4… tối đa 60 giây cộng jitter;
  chạy thành công thì trở về 0,5 giây. Trong thời gian database lỗi, xử lý có thể
  chậm; trạng thái persisted không bị xóa. Không giãn chu kỳ khi hoạt động bình thường.
- Khi shutdown, hủy task và đóng listener. Không đổi schema, không thêm index hay
  dependency production mới, không cần migration dữ liệu.

## Giai đoạn 2 đã thực hiện: realtime audio

Thêm endpoint `/api/v1/detection/alerts/stream`. Sau handshake, client gửi frame
`AUTH` chứa access token; token không nằm trong URL. Backend dùng cùng hàm xác
thực của HTTP, không nhận user_id do client chỉ định. Socket chỉ đọc dữ liệu;
confirm/cancel vẫn dùng API HTTP và transaction hiện tại.

Mỗi user/process dùng chung một feed giữa các thiết bị. Feed nghe con trỏ
`audio_alert_users`, document alert hiện tại, outbox của alert đó, phiên SOS liên
quan và document account. Tất cả instance nghe Firestore trực tiếp nên thay đổi
ở instance A vẫn tới thiết bị kết nối instance B. Không dùng broadcast RAM làm
nguồn đồng bộ. Khi không còn thiết bị, feed và các listener được giải phóng.

Callback chỉ báo dữ liệu có thể đã thay đổi; service hiện tại dựng lại response.
Backend đối soát mỗi 60 giây, nối lại listener chết, gửi heartbeat mỗi 2 giây.
Mỗi response data được xác thực lại trước khi gửi; token/account cũng được kiểm
tra lại khi kết nối nhàn rỗi khoảng mỗi 60 giây. Account listener giúp phát hiện
khóa tài khoản giữa phiên. Client chuyển qua HTTP fallback khi socket đóng,
không có frame quá 5 giây, không có state quá 90 giây, hoặc không áp dụng được
response. Có backoff reconnect 1–30 giây. Interceptor HTTP hiện tại tiếp tục xử lý
refresh token trước khi client đọc token để mở lại socket.

Khi realtime tốt, timer kiểm tra kết nối mỗi giây chỉ dùng RAM, không gọi HTTP.
Khi lỗi, giữ polling mỗi giây như bản cũ để không làm chậm đồng bộ cảnh báo.
Resume tải lại state và mở socket mới; logout đóng socket, hủy timer, loại callback
và response từ phiên cũ. Mốc server_time được làm mới khi gửi để thiết bị mới
không dùng giờ cũ của feed và kéo dài sai đếm ngược 10 giây. Vòng đời nhận cảnh báo
được tách khỏi vòng đời micro: tắt micro không bỏ cảnh báo đã được server nhận.

Ước lượng nhàn rỗi, một thiết bị/user, không có alert, một process, kết nối ổn
định: từ khoảng 172.800 read/ngày (account + con trỏ mỗi giây) xuống khoảng
2.880 read/ngày (con trỏ + xác thực mỗi phút), chưa tính bootstrap, listener,
reconnect, HTTP ban đầu/resume và các luồng khác. Đây là phép tính lý thuyết,
không phải usage đo production. Có SOS/outbox/thay đổi vị trí sẽ phát sinh thêm
read cần thiết. Các client cũ tiếp tục polling cho tới khi cập nhật frontend.

Trong giai đoạn 2, không sửa file backend/frontend của Safety Check: đối chiếu
hash 26 file `.py`/`.dart` với đầu bước này cho kết quả không thay đổi. Giữ nguyên
nghiệp vụ start, grace period, giới hạn gia hạn, confirm-safe, cancel, escalate và
All-Clear; bổ sung regression test cho các hợp đồng này. Các tối ưu scheduler ở
giai đoạn 1 vẫn được giữ nguyên như lúc bắt đầu giai đoạn 2.

## Kiểm thử và triển khai

Chạy offline từ `backend`:

```powershell
python -m pytest tests -q
python -m compileall -q app
git diff --check
```

Các unit test dùng fake I/O, không dùng credentials và không gửi Telegram; bao
gồm snapshot thêm/sửa/xóa, listener lỗi/reconnect, đối soát, quota, countdown,
ownership, cancel sát deadline, lease, retry, token, restart và session kết thúc.
Có kiểm thử ASGI WebSocket với fake Firestore, chia sẻ feed giữa thiết bị và
instance, auth, token/account bị từ chối và cleanup. Chưa chạy Firestore emulator
hoặc production và chưa deploy. Frontend có test realtime và vòng đời phiên;
`flutter analyze` trên file thay đổi và `flutter build web --no-pub` dùng để kiểm tra build.

Sau deploy, đối chiếu Usage trước/sau trong Firebase, test tạo/hủy/xác nhận cảnh
báo trên hai thiết bị, timeout SOS, Telegram, Safety Check và restart khi đang
pending. Nếu quota đã cạn thì sửa code không khôi phục hạn mức đã dùng: cần chờ
reset hoặc xử lý quota/billing tương ứng. Giữ health check `/health`; không đổi
sang endpoint luôn trả 200 để che việc database đang lỗi.

Triển khai backend trước rồi cập nhật frontend. Không cần đổi biến môi trường:
client suy ra URL `ws`/`wss` và prefix từ `API_BASE_URL`. Nếu proxy chưa hỗ trợ
WebSocket hoặc backend cũ chưa có route mới, HTTP fallback vẫn hoạt động.
Không cần migration dữ liệu hay composite index mới. Bộ test bổ sung cài qua
`python -m pip install -r requirements-dev.txt`; frontend chạy `flutter test test`.

Kết quả kiểm tra giai đoạn 2: 42 test backend, 10 test frontend đã qua; phân tích
mã Flutter trên các file thay đổi không báo lỗi. Build web JavaScript thành công.
Heartbeat dùng RAM, không đọc Firestore; ngưỡng socket im lặng 5 giây được chọn
để quay về HTTP trong cửa sổ đếm ngược audio 10 giây khi riêng kênh WS bị treo.
