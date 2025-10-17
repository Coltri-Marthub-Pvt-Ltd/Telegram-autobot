<?php
session_start();

// Default credentials
$default_email = "admin@gmail.com";
$default_password = "12345678";

// LOGIN LOGIC
if (isset($_POST['login'])) {
    $email = $_POST['email'];
    $password = $_POST['password'];

    if ($email === $default_email && $password === $default_password) {
        $_SESSION['user'] = $email;
    } else {
        $error = "Invalid Email or Password!";
    }
}

// LOGOUT
if (isset($_GET['logout'])) {
    session_destroy();
    header("Location: index.php");
    exit;
}

// Sample data
$tab1_data = [
    ['groupId' => 1, 'time' => '08:00', 'status' => 'Active'],
    ['groupId' => 2, 'time' => '14:00', 'status' => 'Deactive'],
    ['groupId' => 3, 'time' => '22:00', 'status' => 'Active'],
];
$tab2_data = [
    ['groupId' => 1, 'groupName' => 'Group A'],
    ['groupId' => 2, 'groupName' => 'Group B'],
    ['groupId' => 3, 'groupName' => 'Group C'],
];
?>

<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Modern Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #4361ee;
            --primary-light: #4895ef;
            --secondary: #3f37c9;
            --success: #4cc9f0;
            --danger: #f72585;
            --warning: #f8961e;
            --dark: #1a1d29;
            --light: #f8f9fa;
            --gray: #6c757d;
            --border: #e2e8f0;
            --card-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
            --hover-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        }

        * {
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%);
            font-family: 'Inter', sans-serif;
            color: var(--dark);
            min-height: 100vh;
            padding: 0;
            margin: 0;
        }

        .container {
            max-width: 1200px;
        }

        .card {
            border: none;
            border-radius: 16px;
            box-shadow: var(--card-shadow);
            transition: all 0.3s ease;
            overflow: hidden;
        }

        .card:hover {
            box-shadow: var(--hover-shadow);
        }

        .btn {
            border-radius: 10px;
            font-weight: 500;
            transition: all 0.3s ease;
            padding: 10px 20px;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            border: none;
            box-shadow: 0 4px 12px rgba(67, 97, 238, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.4);
        }

        .btn-danger {
            background: linear-gradient(135deg, var(--danger) 0%, #b5179e 100%);
            border: none;
            box-shadow: 0 4px 12px rgba(247, 37, 133, 0.3);
        }

        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(247, 37, 133, 0.4);
        }

        .btn-tab {
            border-radius: 12px;
            padding: 12px 30px;
            margin-right: 10px;
            font-weight: 600;
            transition: all 0.3s ease;
            background: white;
            color: var(--gray);
            border: 1px solid var(--border);
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
            position: relative;
            overflow: hidden;
        }

        .btn-tab:hover {
            background: #f1f5ff;
            color: var(--primary);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        .btn-tab.active {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
            color: white;
            box-shadow: 0 6px 20px rgba(67, 97, 238, 0.3);
            border: none;
        }

        .btn-tab.active::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: white;
            border-radius: 0 0 10px 10px;
        }

        .table-card {
            border-radius: 16px;
            overflow: hidden;
            box-shadow: var(--card-shadow);
            margin-top: 20px;
            background: white;
            animation: fadeIn 0.5s ease;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }

            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .table {
            margin-bottom: 0;
        }

        .table thead th {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
            color: white;
            border: none;
            padding: 15px 20px;
            font-weight: 600;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .table tbody tr {
            transition: all 0.2s ease;
        }

        .table tbody tr:hover {
            background-color: rgba(67, 97, 238, 0.05);
            transform: translateY(-1px);
        }

        .table tbody td {
            padding: 15px 20px;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }

        .badge {
            padding: 8px 15px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .badge:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }

        .badge-active {
            background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
            color: white;
        }

        .badge-deactive {
            background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
            color: white;
        }

        .btn-delete {
            background: linear-gradient(135deg, var(--danger) 0%, #b5179e 100%);
            border: none;
            color: white;
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 0.85rem;
            transition: all 0.2s ease;
        }

        .btn-delete:hover {
            background: linear-gradient(135deg, #e11d48 0%, #9d174d 100%);
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(247, 37, 133, 0.3);
        }

        .btn-info {
            background: linear-gradient(135deg, var(--success) 0%, #3a86ff 100%);
            border: none;
            color: white;
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 0.85rem;
            transition: all 0.2s ease;
        }

        .btn-info:hover {
            background: linear-gradient(135deg, #3a86ff 0%, #2667cc 100%);
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(76, 201, 240, 0.3);
        }

        .form-control {
            border-radius: 10px;
            padding: 12px 15px;
            border: 1px solid var(--border);
            transition: all 0.3s ease;
        }

        .form-control:focus {
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
            border-color: var(--primary);
        }

        .form-select {
            border-radius: 8px;
            padding: 8px 15px;
            border: 1px solid var(--border);
            transition: all 0.2s ease;
        }

        .form-select:focus {
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
            border-color: var(--primary);
        }

        .login-container {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .login-card {
            max-width: 420px;
            width: 100%;
            padding: 40px;
            background: white;
        }

        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding: 20px 0;
        }

        .dashboard-title {
            font-weight: 700;
            color: var(--dark);
            margin: 0;
            font-size: 2rem;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .tab-container {
            margin-bottom: 25px;
        }

        .no-data {
            text-align: center;
            padding: 40px 20px;
            color: var(--gray);
        }

        .no-data i {
            font-size: 3rem;
            margin-bottom: 15px;
            opacity: 0.5;
        }

        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }

        .status-active {
            background-color: #22c55e;
        }

        .status-deactive {
            background-color: #ef4444;
        }

        @media (max-width: 768px) {
            .btn-tab {
                width: 100%;
                margin-bottom: 10px;
                margin-right: 0;
            }

            .dashboard-header {
                flex-direction: column;
                align-items: flex-start;
            }

            .dashboard-title {
                margin-bottom: 15px;
            }

            .table-card {
                overflow-x: auto;
            }
        }
    </style>
</head>

<body>
    <?php if (!isset($_SESSION['user'])): ?>
        <div class="login-container">
            <div class="card login-card">
                <div class="text-center mb-4">
                    <h3 class="fw-bold">Welcome Back</h3>
                    <p class="text-muted">Sign in to your account</p>
                </div>
                <?php if (!empty($error)): ?>
                    <div class="alert alert-danger d-flex align-items-center" role="alert">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        <div><?php echo $error; ?></div>
                    </div>
                <?php endif; ?>
                <form method="post">
                    <div class="mb-3">
                        <label class="form-label fw-semibold">Email</label>
                        <div class="input-group">
                            <span class="input-group-text bg-light border-end-0"><i class="fas fa-envelope text-muted"></i></span>
                            <input type="email" name="email" class="form-control border-start-0" placeholder="Enter your email" required>
                        </div>
                    </div>
                    <div class="mb-4">
                        <label class="form-label fw-semibold">Password</label>
                        <div class="input-group">
                            <span class="input-group-text bg-light border-end-0"><i class="fas fa-lock text-muted"></i></span>
                            <input type="password" name="password" class="form-control border-start-0" placeholder="Enter your password" required>
                        </div>
                    </div>
                    <button type="submit" name="login" class="btn btn-primary w-100 py-2 fw-semibold">
                        <i class="fas fa-sign-in-alt me-2"></i> Sign In
                    </button>
                </form>
            </div>
        </div>

    <?php else: ?>
        <div class="container py-4">
            <div class="dashboard-header">
                <h1 class="dashboard-title">Welcome Dashboard</h1>
                <a href="?logout=1" class="btn btn-danger">
                    <i class="fas fa-sign-out-alt me-2"></i> Logout
                </a>
            </div>

            <!-- Modern Tab Buttons -->
            <div class="tab-container">
                <button id="tab1-btn" class="btn btn-tab">
                    <i class="fas fa-table me-2"></i> Auto Delete
                </button>
                <button id="tab2-btn" class="btn btn-tab">
                    <i class="fas fa-users me-2"></i> All Delete
                </button>
            </div>

            <!-- Tab Content (hidden by default) -->
            <div id="tab-content">
                <div id="tab1" class="table-card" style="display:none;"></div>
                <div id="tab2" class="table-card" style="display:none;"></div>
            </div>
        </div>
    <?php endif; ?>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const tab1Btn = document.getElementById('tab1-btn');
            const tab2Btn = document.getElementById('tab2-btn');
            const tab1Div = document.getElementById('tab1');
            const tab2Div = document.getElementById('tab2');

            //let tab1Data = <?php echo json_encode($tab1_data); ?>;
            //let tab2Data = <?php echo json_encode($tab2_data); ?>;

            function activateTab(tab) {
                if (tab === 1) {
                    tab1Div.style.display = "block";
                    tab2Div.style.display = "none";
                    tab1Btn.classList.add("active");
                    tab2Btn.classList.remove("active");
                    renderTab1();
                } else {
                    tab1Div.style.display = "none";
                    tab2Div.style.display = "block";
                    tab2Btn.classList.add("active");
                    tab1Btn.classList.remove("active");
                    renderTab2();
                }
            }

            function renderTab1() {
                if (tab1Data.length === 0) {
                    tab1Div.innerHTML = `
                <div class="no-data">
                    <i class="fas fa-table"></i>
                    <h4>No Data Available</h4>
                    <p>There are no records to display in Tab 1.</p>
                </div>
            `;
                    return;
                }

                let html = `<table class="table table-hover align-middle">
                        <thead>
                        <tr><th>Group ID</th><th>Time</th><th>Status</th></tr>
                        </thead><tbody>`;
                tab1Data.forEach(row => {
                    html += `<tr>
                        <td class="fw-semibold">${row.groupId}</td>
                        <td><select class="form-select time-select" data-id="${row.groupId}">`;
                    for (let i = 0; i < 24; i++) {
                        let hour = (i < 10 ? "0" + i : i) + ":00";
                        let selected = (hour === row.time) ? "selected" : "";
                        html += `<option value="${hour}" ${selected}>${hour}</option>`;
                    }
                    html += `</select></td>`;
                    let statusClass = row.status === "Active" ? "badge-active" : "badge-deactive";
                    let statusIndicator = row.status === "Active" ? "status-active" : "status-deactive";
                    html += `<td>
                      <span class="badge ${statusClass} status-btn" data-id="${row.groupId}">
                        <span class="status-indicator ${statusIndicator}"></span>
                        ${row.status}
                      </span>
                   </td>`;
                    html += `</tr>`;
                });
                html += `</tbody></table>`;
                tab1Div.innerHTML = html;

                document.querySelectorAll('.status-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        const groupId = this.dataset.id;
                        const newStatus = this.textContent.trim() === "Active" ? "Deactive" : "Active";
                        setTimeout(() => {
                            alert("Group " + groupId + " status changed to " + newStatus);
                            this.textContent = newStatus;
                            this.classList.toggle('badge-active');
                            this.classList.toggle('badge-deactive');

                            // Update status indicator
                            const indicator = this.querySelector('.status-indicator');
                            indicator.classList.toggle('status-active');
                            indicator.classList.toggle('status-deactive');
                        }, 200);
                    });
                });
            }

          // const tab2Div = document.getElementById("tab2Div"); // your tab2 container div
    let tab2Data = [];

    // ✅ Fetch Telegram groups from API
    async function loadGroups() {
            try {
                const response = await fetch("http://senti.royalpepperbanquets.in:8000/groups?tag=A");
                const data = await response.json();
					console.log("data=" + JSON.stringify(data));
                tab2Data = data.map(group => ({
                    groupId: group.group_id,
                    groupName: group.group_name
                }));

                renderTab2();
            } catch (error) {
                console.error("Error fetching groups:", error);
                tab2Div.innerHTML = `<p style="color:red;">❌ Failed to load groups. Check server or CORS settings.</p>`;
            }
        }

    // ✅ Render table
    function renderTab2() {
            if (tab2Data.length === 0) {
                tab2Div.innerHTML = `
                    <div class="no-data">
                        <i class="fas fa-users"></i>
                        <h4>No Groups Available</h4>
                        <p>There are no groups to display.</p>
                    </div>
                `;
                return;
            }

            let html = `
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <div>
                        <button id="selectAll" class="btn btn-info btn-sm me-2">
                            <i class="fas fa-check-square me-1"></i> Select All
                        </button>
                        <button id="unselectAll" class="btn btn-secondary btn-sm">
                            <i class="fas fa-square me-1"></i> Unselect All
                        </button>
                    </div>
                    <button id="purgeSelected" class="btn btn-danger btn-sm">
                        <i class="fas fa-trash-alt me-1"></i> Purge Selected
                    </button>
                </div>

                <table class="table table-hover align-middle">
                    <thead>
                        <tr>
                            <th><input type="checkbox" id="selectAllCheckbox"></th>
                            <th>Group ID</th>
                            <th>Group Name</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            tab2Data.forEach((row, index) => {
                html += `
                    <tr data-index="${index}">
                        <td><input type="checkbox" class="group-checkbox" value="${row.groupId}"></td>
                        <td class="fw-semibold">${row.groupId}</td>
                        <td>${row.groupName}</td>
                        <td>
                            <button class='btn btn-danger btn-sm purge-btn' data-id="${row.groupId}" data-name="${row.groupName}">
                                <i class='fas fa-broom me-1'></i> Purge
                            </button>
                        </td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;
            tab2Div.innerHTML = html;

            // ✅ Select / Unselect all logic
            document.getElementById("selectAll").addEventListener("click", () => {
                document.querySelectorAll(".group-checkbox").forEach(cb => cb.checked = true);
            });
            document.getElementById("unselectAll").addEventListener("click", () => {
                document.querySelectorAll(".group-checkbox").forEach(cb => cb.checked = false);
            });

            const selectAllCheckbox = document.getElementById("selectAllCheckbox");
            selectAllCheckbox.addEventListener("change", function () {
                const isChecked = this.checked;
                document.querySelectorAll(".group-checkbox").forEach(cb => cb.checked = isChecked);
            });

            // ✅ Purge selected groups
            document.getElementById("purgeSelected").addEventListener("click", async function () {
                const selected = Array.from(document.querySelectorAll(".group-checkbox:checked"))
                    .map(cb => cb.value);

                if (selected.length === 0) {
                    alert("⚠️ No groups selected!");
                    return;
                }
				//console.log(selected.join(","));
				//return;
                const confirmPurge = confirm(`Are you sure you want to purge these groups?\nIDs: ${selected.join(", ")}`);
                if (!confirmPurge) return;

                try {
                    const response = await fetch("http://senti.royalpepperbanquets.in:8000/actions/purge", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ group_ids: selected })
                    });

                    if (response.ok) {
                        alert(`✅ Selected groups purged successfully!`);
                    } else {
                        const err = await response.text();
                        alert(`❌ Failed to purge selected groups: ${err}`);
                    }
                } catch (err) {
                    alert("⚠️ Error connecting to server: " + err.message);
                }
            });

            // ✅ Individual purge buttons
            document.querySelectorAll('.purge-btn').forEach(btn => {
                btn.addEventListener('click', async function () {
                    const groupId = this.dataset.id;
                    const groupName = this.dataset.name;
					
                    if (!confirm(`Are you sure you want to purge "${groupName}" (ID: ${groupId})?`)) return;

                    try {
                        const response = await fetch("http://senti.royalpepperbanquets.in:8000/actions/purge", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ group_ids: [groupId] })
                        });

                        if (response.ok) {
                            alert(`✅ Group "${groupName}" purged successfully!`);
                        } else {
                            const err = await response.text();
                            alert(`❌ Failed to purge group: ${err}`);
                        }
                    } catch (err) {
                        alert("⚠️ Error connecting to server: " + err.message);
                    }
                });
            });
        }

        // ✅ Load groups on page load
        loadGroups();
			
			
    // ✅ Call API on page load
    loadGroups();
            // Tab buttons click
            tab1Btn.addEventListener('click', () => activateTab(1));
            tab2Btn.addEventListener('click', () => activateTab(2));

            // **No tab shown by default**
        });
    </script>
</body>

</html>