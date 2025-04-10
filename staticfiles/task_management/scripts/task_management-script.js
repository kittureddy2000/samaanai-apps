function formatDate(dateString) {
  if (!dateString || isNaN(new Date(dateString))) {
    return "No Due Date"; // Handle null or invalid dates
  }

  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const date = new Date(dateString);

  // Ensure the date is valid before extracting components
  if (isNaN(date.getTime())) {
    return "Invalid Date";
  }

  const day = date.getDate();
  const monthIndex = date.getMonth();
  const year = date.getFullYear().toString().substr(-2); // Get last two digits of the year
  const formattedDate = `${day}-${months[monthIndex]}-${year}`;

  const today = new Date();
  today.setHours(0, 0, 0, 0); // Normalize to start of the day
  //console.log("formattedDate: ", formattedDate);

  if (date < today) {
    // If the date is in the past, wrap it in a span with text-danger class
    return `<span class="text-danger">${formattedDate}</span>`;
  } else {
    return formattedDate;
  }
}
