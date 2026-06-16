(function () {
    const forms = document.querySelectorAll(".manager-routing-form");

    forms.forEach((form) => {
        const roleSelect = form.querySelector("select[name='role']");
        const managerSelect = form.querySelector("select[name='managed_by']");
        const catalogNode = form.querySelector("#manager-catalog");

        if (!roleSelect || !managerSelect || !catalogNode) {
            return;
        }

        const catalog = JSON.parse(catalogNode.textContent);

        const optionSets = {
            worker: {
                placeholder: { value: "0", label: "Select supervisor" },
                options: catalog.supervisors || [],
            },
            supervisor: {
                placeholder: { value: "0", label: "Use current admin" },
                options: catalog.admins || [],
            },
            ngo: {
                placeholder: { value: "0", label: "Use current admin" },
                options: catalog.admins || [],
            },
            admin: {
                placeholder: { value: "0", label: "System / none" },
                options: [],
            },
            citizen: {
                placeholder: { value: "0", label: "System / none" },
                options: [],
            },
        };

        const renderOptions = () => {
            const selectedValue = managerSelect.value;
            const config = optionSets[roleSelect.value] || optionSets.citizen;
            managerSelect.innerHTML = "";

            const placeholder = document.createElement("option");
            placeholder.value = config.placeholder.value;
            placeholder.textContent = config.placeholder.label;
            managerSelect.appendChild(placeholder);

            config.options.forEach((entry) => {
                const option = document.createElement("option");
                option.value = String(entry.id);
                option.textContent = entry.label;
                managerSelect.appendChild(option);
            });

            const allowedValues = new Set(
                [config.placeholder.value, ...config.options.map((entry) => String(entry.id))]
            );
            managerSelect.value = allowedValues.has(selectedValue) ? selectedValue : config.placeholder.value;
        };

        roleSelect.addEventListener("change", renderOptions);
        renderOptions();
    });
})();
