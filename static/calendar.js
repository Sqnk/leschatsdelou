document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');

    if (!calendarEl) {
        console.error("⚠️ #calendar introuvable dans la page.");
        return;
    }

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'fr',
        height: 'auto',

        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,listWeek'
        },

        events: '/api/appointments',  // API renvoyant JSON {title, start, id}

        eventDidMount: function (info) {
            // Ajout d’un tooltip lisible
            let tooltip = new bootstrap.Tooltip(info.el, {
                title: info.event.extendedProps.fullInfo || info.event.title,
                placement: 'top',
                trigger: 'hover',
                container: 'body'
            });
        },

        eventClick: function (info) {
            // Clique sur un RDV → ouverture de la fiche
            window.location.href = '/appointments';
        }
    });

    calendar.render();
});
