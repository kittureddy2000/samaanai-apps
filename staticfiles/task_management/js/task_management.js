// function createTaskCardHTML(task) {
//     const taskNameClass = task.task_completed ? 'strikethrough' : '';
//     const checkIcon = task.task_completed ? 'far fa-check-circle' : 'far fa-circle';
//     const favoriteIconClass = task.important ? 'far fa-star text-primary' : 'far fa-star';
//     const dueDateText = task.due_date ? formatDate(task.due_date) : '';
//     const overdueText = task.overdue ? ' · Overdue' : '';
    
//     return `
//       <div class="task-card" data-task-id="${task.id}" id="task-${task.id}">
//         <div class="d-flex justify-content-between align-items-center">
//           <div class="d-flex align-items-center">
//             <i class="${checkIcon} custom-check" data-id="${task.id}"></i>
//             <div>
//               <div class="task-name ${taskNameClass}">${task.task_name}</div>
//               ${dueDateText ? `<div class="task-due-date">${dueDateText}${overdueText}</div>` : ''}
//             </div>
//           </div>
//           <i class="${favoriteIconClass} mark-favorite" data-id="${task.id}"></i>
//         </div>
//       </div>`;
//   }